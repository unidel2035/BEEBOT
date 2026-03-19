"""Structured JSON-логирование для сервисов BEEBOT.

Вызывать setup_logging() один раз при старте сервиса (в main() или lifespan).
Не вызывать в тестах — иначе pytest output будет в JSON-формате.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Форматирует каждую запись лога как одну строку JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "time": (
                datetime.fromtimestamp(record.created, tz=timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """Переключить корневой логгер на JSON-формат.

    Подавляет INFO-шум от сторонних библиотек (httpx, httpcore).
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Подавить HTTP-трейс сторонних библиотек
    for lib in ("httpx", "httpcore", "multipart"):
        logging.getLogger(lib).setLevel(logging.WARNING)
