"""Тесты BackgroundTaskManager."""

import asyncio

import pytest
from unittest.mock import AsyncMock

from src.web.bg_tasks import BackgroundTaskManager

pytestmark = pytest.mark.asyncio


async def test_start_and_status():
    mgr = BackgroundTaskManager()

    async def dummy():
        await asyncio.sleep(100)

    await mgr.start("test_task", dummy)
    status = mgr.status()

    assert "test_task" in status
    assert status["test_task"]["state"] == "работает"
    assert status["test_task"]["restarts"] == 0

    await mgr.stop_all()


async def test_stop_task():
    mgr = BackgroundTaskManager()

    async def dummy():
        await asyncio.sleep(100)

    await mgr.start("stoppable", dummy)
    await mgr.stop("stoppable")

    status = mgr.status()
    assert status["stoppable"]["state"] in ("отменена", "не запущена")


async def test_stop_all():
    mgr = BackgroundTaskManager()

    async def dummy():
        await asyncio.sleep(100)

    await mgr.start("task1", dummy)
    await mgr.start("task2", dummy)

    assert len(mgr.status()) == 2

    await mgr.stop_all()

    for info in mgr.status().values():
        assert info["state"] != "работает"


async def test_auto_restart_on_crash():
    mgr = BackgroundTaskManager()
    call_count = 0

    async def crasher():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        await asyncio.sleep(100)

    await mgr.start("crasher", crasher)

    # Подождать авто-рестарт (delay=2 сек для рестарта #1)
    await asyncio.sleep(3)

    assert call_count >= 2
    assert mgr.status()["crasher"]["restarts"] >= 1

    await mgr.stop_all()


async def test_alert_on_crash():
    alert_fn = AsyncMock()
    mgr = BackgroundTaskManager(alert_fn=alert_fn)

    async def crasher():
        raise ValueError("test error")

    await mgr.start("alerter", crasher)
    await asyncio.sleep(3)

    alert_fn.assert_called()
    alert_text = alert_fn.call_args[0][0]
    assert "alerter" in alert_text
    assert "test error" in alert_text

    await mgr.stop_all()


async def test_status_completed_task():
    mgr = BackgroundTaskManager()

    async def quick():
        return  # завершается сразу

    await mgr.start("quick", quick)
    await asyncio.sleep(0.5)

    status = mgr.status()
    assert status["quick"]["state"] == "завершена"

    await mgr.stop_all()


async def test_duplicate_start_ignored():
    mgr = BackgroundTaskManager()

    async def dummy():
        await asyncio.sleep(100)

    await mgr.start("dup", dummy)
    await mgr.start("dup", dummy)  # дублирует — должно предупредить

    # Только одна задача
    assert mgr.status()["dup"]["state"] == "работает"

    await mgr.stop_all()
