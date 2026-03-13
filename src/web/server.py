"""Точка входа для uvicorn — монтирует FastAPI API и раздаёт Vue SPA.

Структура:
  /api/...  — FastAPI эндпоинты (из api.py)
  /*        — статические файлы Vue (web/dist/)

Запуск:
  uvicorn src.web.server:app --host 0.0.0.0 --port 8080
"""

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.web.api import app

_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


# Монтируем статику Vue (assets/, favicon.svg и т.д.)
if _DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str) -> FileResponse:
        """Fallback для Vue Router (HTML5 history mode)."""
        # Если запрос идёт к /api — не перехватываем (FastAPI обработает раньше)
        index = _DIST_DIR / "index.html"
        return FileResponse(str(index))
