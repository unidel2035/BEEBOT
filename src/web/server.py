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

# Файлы PWA, которые должны раздаваться из корня (не через SPA fallback)
_PWA_ROOT_FILES = {
    "manifest.webmanifest", "sw.js", "workbox-*.js",
    "icon-192.png", "icon-512.png", "favicon.svg",
    "registerSW.js",
}


def _is_root_static(path: str) -> bool:
    """Проверить, является ли путь корневым статическим файлом."""
    name = path.lstrip("/")
    if not name or "/" in name:
        return False
    for pattern in _PWA_ROOT_FILES:
        if "*" in pattern:
            prefix = pattern.split("*")[0]
            if name.startswith(prefix):
                return True
        elif name == pattern:
            return True
    return False


# Монтируем статику Vue (assets/, favicon.svg и т.д.)
if _DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str) -> FileResponse:
        """Fallback для Vue Router (HTML5 history mode).

        Корневые файлы PWA (manifest, sw.js, иконки) отдаются напрямую.
        Всё остальное — index.html (SPA).
        """
        # PWA-файлы из корня dist/
        if _is_root_static(full_path):
            static_file = _DIST_DIR / full_path
            if static_file.exists():
                return FileResponse(str(static_file))

        index = _DIST_DIR / "index.html"
        return FileResponse(str(index))
