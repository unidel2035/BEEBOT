"""BackgroundTaskManager — управление фоновыми задачами Backend.

Заменяет fire-and-forget asyncio.create_task() на управляемый менеджер
с мониторингом, автоперезапуском при падении и алертами.

Задачи:
- CRM Snapshot (каждые 5 мин)
- OrderTracker (каждые 2 часа)
- UDS Poller (каждые 5 мин)
- TunnelMonitor (каждые 60 сек)
- BackupManager (ежедневно)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

TaskFactory = Callable[[], Coroutine[Any, Any, None]]


class BackgroundTaskManager:
    """Менеджер фоновых задач с мониторингом и авто-рестартом."""

    def __init__(self, alert_fn: Optional[Callable[[str], Coroutine]] = None):
        """
        Args:
            alert_fn: async функция для отправки алертов (напр. в Telegram).
        """
        self._tasks: dict[str, asyncio.Task] = {}
        self._factories: dict[str, TaskFactory] = {}
        self._started_at: dict[str, float] = {}
        self._restart_count: dict[str, int] = {}
        self._alert_fn = alert_fn
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, name: str, factory: TaskFactory) -> None:
        """Запустить фоновую задачу.

        Args:
            name: Уникальное имя задачи.
            factory: Async-функция (coroutine factory) — вызывается при старте и рестарте.
        """
        if name in self._tasks and not self._tasks[name].done():
            logger.warning("BGTask: задача '%s' уже запущена", name)
            return

        self._factories[name] = factory
        self._restart_count.setdefault(name, 0)
        await self._launch(name)
        self._running = True

    async def stop(self, name: str) -> None:
        """Остановить конкретную задачу."""
        task = self._tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("BGTask: задача '%s' остановлена", name)

    async def stop_all(self) -> None:
        """Graceful shutdown всех задач."""
        self._running = False
        names = list(self._tasks.keys())
        for name in names:
            await self.stop(name)
        logger.info("BGTask: все задачи остановлены")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, dict]:
        """Состояние всех задач для /api/health и /admin."""
        result = {}
        for name in self._factories:
            task = self._tasks.get(name)
            if task is None:
                state = "не запущена"
            elif task.done():
                state = "завершена" if not task.cancelled() else "отменена"
                if task.exception():
                    state = f"упала: {task.exception()}"
            else:
                state = "работает"

            uptime = time.time() - self._started_at.get(name, time.time())
            result[name] = {
                "state": state,
                "uptime_sec": round(uptime),
                "restarts": self._restart_count.get(name, 0),
            }
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _launch(self, name: str) -> None:
        """Запустить задачу и зарегистрировать callback."""
        factory = self._factories[name]
        coro = factory()
        task = asyncio.create_task(coro, name=f"bg:{name}")
        task.add_done_callback(lambda t: asyncio.create_task(self._on_done(name, t)))
        self._tasks[name] = task
        self._started_at[name] = time.time()
        logger.info("BGTask: задача '%s' запущена", name)

    async def _on_done(self, name: str, task: asyncio.Task) -> None:
        """Callback при завершении задачи — авто-рестарт при падении."""
        if not self._running:
            return  # shutdown, не перезапускать

        if task.cancelled():
            return

        exc = task.exception()
        if exc:
            self._restart_count[name] = self._restart_count.get(name, 0) + 1
            logger.error(
                "BGTask: задача '%s' упала (рестарт #%d): %s",
                name, self._restart_count[name], exc,
            )
            await self._alert(
                f"⚠️ Задача {name} упала (рестарт #{self._restart_count[name]}): {exc}"
            )

            # Пауза перед рестартом (экспоненциальная, макс 60 сек)
            delay = min(2 ** self._restart_count[name], 60)
            await asyncio.sleep(delay)

            if self._running and name in self._factories:
                await self._launch(name)
        else:
            logger.info("BGTask: задача '%s' завершилась штатно", name)

    async def _alert(self, text: str) -> None:
        """Отправить алерт (best-effort)."""
        if self._alert_fn:
            try:
                await self._alert_fn(text)
            except Exception as e:
                logger.warning("BGTask: ошибка алерта: %s", e)
