"""Удаление заказов-дублей без позиций из Integram v2.

Дубли создались сломанным скриптом синхронизации UDS: заказы без позиций.
Настоящие заказы имеют хотя бы одну позицию в дочерней таблице (TABLE_ORDER_ITEMS).

Алгоритм:
  1. Получить ВСЕ ID заказов через REST-пагинацию
  2. Получить parent_map из таблицы позиций → узнать какие заказы реальные
  3. Дубли = order_ids, которых нет в set(parent_map.values())
  4. Удалить через REST DELETE /api/v2/{workspace}/objects/{id}

Запуск:
    cd /home/hive/BEEBOT
    python scripts/cleanup_duplicate_orders.py [--dry-run] [--limit 100]

Параметры:
    --dry-run    Не удалять, только показать что будет удалено
    --limit N    Максимальное число удалений за раз (защита от ошибок)
    --yes        Не спрашивать подтверждение (авто-да)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import config  # noqa: F401 — загружает .env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

import os

BASE_URL = os.getenv("INTEGRAM_V2_URL", "https://ai2o.online").rstrip("/")
EMAIL = os.getenv("INTEGRAM_V2_EMAIL", "")
PASSWORD = os.getenv("INTEGRAM_V2_PASSWORD", "")
WORKSPACE = os.getenv("INTEGRAM_V2_WORKSPACE", "alekseymavai")

TABLE_ORDERS = 2165       # typeId таблицы заказов
TABLE_ORDER_ITEMS = 2166  # typeId таблицы позиций

PAGE_SIZE = 50
BATCH_SIZE = 5          # параллельных запросов за раз
BATCH_PAUSE = 0.3       # секунд между батчами (не перегружать сервер)
DELETE_BATCH_SIZE = 5   # параллельных удалений за раз
DELETE_PAUSE = 0.5      # секунд между батчами удалений


# ---------------------------------------------------------------------------
# HTTP-клиент
# ---------------------------------------------------------------------------

class IntegramCleaner:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30)
        self._token: str | None = None

    async def authenticate(self) -> None:
        resp = await self._client.post(
            f"{BASE_URL}/api/v2/iam/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("accessToken")
        if not self._token:
            raise RuntimeError(f"Нет accessToken в ответе: {data}")
        logger.info("Аутентификация успешна")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Загрузка всех ID заказов
    # ------------------------------------------------------------------

    async def _fetch_orders_page(self, page: int) -> list[int]:
        """Получить ID заказов со страницы."""
        for attempt in range(3):
            try:
                r = await self._client.get(
                    f"{BASE_URL}/api/v2/{WORKSPACE}/objects",
                    params={"typeId": TABLE_ORDERS, "max": PAGE_SIZE, "page": page},
                    headers=self._headers(),
                )
                r.raise_for_status()
                return [row["id"] for row in r.json().get("data", []) if row.get("id")]
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException):
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning("Таймаут на стр. %d заказов — пропуск", page)
                    return []

    async def fetch_all_order_ids(self) -> list[int]:
        """Получить ВСЕ ID заказов через постраничную загрузку."""
        logger.info("Загрузка ID всех заказов...")

        # Страница 1 — узнаём мета
        r = await self._client.get(
            f"{BASE_URL}/api/v2/{WORKSPACE}/objects",
            params={"typeId": TABLE_ORDERS, "max": PAGE_SIZE, "page": 1},
            headers=self._headers(),
        )
        r.raise_for_status()
        first = r.json()
        meta = first.get("meta", {})
        total_pages = meta.get("totalPages", 1)
        total_records = meta.get("total", "?")
        logger.info("Заказов в БД: %s, страниц: %d", total_records, total_pages)

        ids: list[int] = [row["id"] for row in first.get("data", []) if row.get("id")]

        pages_to_fetch = list(range(2, total_pages + 1))
        for i in range(0, len(pages_to_fetch), BATCH_SIZE):
            batch = pages_to_fetch[i:i + BATCH_SIZE]
            results = await asyncio.gather(*[self._fetch_orders_page(p) for p in batch])
            for page_ids in results:
                ids.extend(page_ids)
            if i + BATCH_SIZE < len(pages_to_fetch):
                await asyncio.sleep(BATCH_PAUSE)

        logger.info("Всего ID заказов: %d", len(ids))
        return ids

    # ------------------------------------------------------------------
    # Загрузка parent_map (позиции → заказы)
    # ------------------------------------------------------------------

    async def _fetch_items_page(self, page: int) -> list[tuple[int, int]]:
        """Получить [(item_id, order_id)] со страницы позиций."""
        for attempt in range(3):
            try:
                r = await self._client.get(
                    f"{BASE_URL}/api/v2/{WORKSPACE}/objects",
                    params={"typeId": TABLE_ORDER_ITEMS, "max": PAGE_SIZE, "page": page},
                    headers=self._headers(),
                )
                r.raise_for_status()
                rows = r.json().get("data", [])
                result = []
                for row in rows:
                    item_id = row.get("id")
                    parent_id = row.get("parentId")
                    if item_id and parent_id and parent_id != 1:
                        result.append((item_id, parent_id))
                return result
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException):
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning("Таймаут на стр. %d позиций — пропуск", page)
                    return []

    async def fetch_order_ids_with_items(self) -> set[int]:
        """Получить множество order_id которые имеют позиции."""
        logger.info("Загрузка parent_map (позиции → заказы)...")

        r = await self._client.get(
            f"{BASE_URL}/api/v2/{WORKSPACE}/objects",
            params={"typeId": TABLE_ORDER_ITEMS, "max": PAGE_SIZE, "page": 1},
            headers=self._headers(),
        )
        r.raise_for_status()
        first = r.json()
        meta = first.get("meta", {})
        total_pages = meta.get("totalPages", 1)
        total_items = meta.get("total", "?")
        logger.info("Позиций в БД: %s, страниц: %d", total_items, total_pages)

        order_ids_with_items: set[int] = set()
        for row in first.get("data", []):
            parent_id = row.get("parentId")
            if parent_id and parent_id != 1:
                order_ids_with_items.add(parent_id)

        pages_to_fetch = list(range(2, total_pages + 1))
        for i in range(0, len(pages_to_fetch), BATCH_SIZE):
            batch = pages_to_fetch[i:i + BATCH_SIZE]
            results = await asyncio.gather(*[self._fetch_items_page(p) for p in batch])
            for pairs in results:
                for _, order_id in pairs:
                    order_ids_with_items.add(order_id)
            if i + BATCH_SIZE < len(pages_to_fetch):
                await asyncio.sleep(BATCH_PAUSE)

        logger.info("Заказов с позициями: %d", len(order_ids_with_items))
        return order_ids_with_items

    # ------------------------------------------------------------------
    # Удаление
    # ------------------------------------------------------------------

    async def _delete_one(self, order_id: int) -> bool:
        """Удалить один заказ через REST DELETE. Вернуть True при успехе."""
        for attempt in range(3):
            try:
                r = await self._client.delete(
                    f"{BASE_URL}/api/v2/{WORKSPACE}/objects/{order_id}",
                    headers=self._headers(),
                )
                if r.status_code in (200, 204):
                    return True
                # Попробовать через AI-tool если REST DELETE не работает
                r2 = await self._client.post(
                    f"{BASE_URL}/api/v2/{WORKSPACE}/ai/tool",
                    json={"name": "delete_object", "args": {"objectId": order_id}, "skipHitl": True},
                    headers=self._headers(),
                )
                data = r2.json()
                if data.get("ok"):
                    return True
                logger.warning("Не удалось удалить %d: %s", order_id, data.get("error"))
                return False
            except (httpx.ConnectTimeout, httpx.ReadTimeout):
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error("Таймаут при удалении %d", order_id)
                    return False
        return False

    async def delete_duplicates(
        self,
        duplicate_ids: list[int],
        dry_run: bool = True,
        limit: int | None = None,
    ) -> tuple[int, int]:
        """Удалить дубли. Вернуть (удалено, ошибок)."""
        ids_to_delete = duplicate_ids[:limit] if limit else duplicate_ids

        if dry_run:
            logger.info(
                "[DRY-RUN] Будет удалено %d заказов-дублей (из %d итого)",
                len(ids_to_delete), len(duplicate_ids),
            )
            if ids_to_delete:
                sample = ids_to_delete[:10]
                logger.info("[DRY-RUN] Первые %d ID: %s", len(sample), sample)
            return 0, 0

        deleted = 0
        errors = 0
        total = len(ids_to_delete)

        logger.info("Удаление %d заказов-дублей...", total)
        for i in range(0, total, DELETE_BATCH_SIZE):
            batch = ids_to_delete[i:i + DELETE_BATCH_SIZE]
            results = await asyncio.gather(*[self._delete_one(oid) for oid in batch])
            for ok in results:
                if ok:
                    deleted += 1
                else:
                    errors += 1
            if i + DELETE_BATCH_SIZE < total:
                await asyncio.sleep(DELETE_PAUSE)
            if (i + DELETE_BATCH_SIZE) % 100 < DELETE_BATCH_SIZE:
                logger.info(
                    "Прогресс: %d/%d удалено, %d ошибок",
                    deleted, total, errors,
                )

        return deleted, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    if not EMAIL or not PASSWORD:
        logger.error("INTEGRAM_V2_EMAIL / INTEGRAM_V2_PASSWORD не заданы в .env")
        sys.exit(1)

    cleaner = IntegramCleaner()
    try:
        await cleaner.authenticate()

        all_order_ids = await cleaner.fetch_all_order_ids()
        order_ids_with_items = await cleaner.fetch_order_ids_with_items()

        duplicate_ids = [oid for oid in all_order_ids if oid not in order_ids_with_items]

        logger.info("=" * 60)
        logger.info("Всего заказов в БД:       %d", len(all_order_ids))
        logger.info("Заказов с позициями:      %d", len(order_ids_with_items))
        logger.info("Заказов-дублей (без поз): %d", len(duplicate_ids))
        logger.info("=" * 60)

        if not duplicate_ids:
            logger.info("Дублей нет — ничего удалять не нужно.")
            return

        if args.dry_run:
            await cleaner.delete_duplicates(duplicate_ids, dry_run=True, limit=args.limit)
            logger.info("Dry-run завершён. Для реального удаления уберите --dry-run и добавьте --yes")
            return

        # Подтверждение (если не --yes)
        if not args.yes:
            count = min(len(duplicate_ids), args.limit) if args.limit else len(duplicate_ids)
            print(f"\n⚠️  Будет УДАЛЕНО {count} заказов без позиций из Integram CRM.")
            print(f"   Первые 10 ID: {duplicate_ids[:10]}")
            answer = input("Введите 'да' для подтверждения: ").strip().lower()
            if answer not in ("да", "yes", "y"):
                logger.info("Отменено пользователем.")
                return

        deleted, errors = await cleaner.delete_duplicates(
            duplicate_ids, dry_run=False, limit=args.limit,
        )
        logger.info("=" * 60)
        logger.info("Удалено: %d, ошибок: %d", deleted, errors)
        logger.info("=" * 60)

    finally:
        await cleaner.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Удаление заказов-дублей без позиций")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Только показать, не удалять (default: ON)")
    parser.add_argument("--execute", action="store_true",
                        help="Реальное удаление (выключает --dry-run)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Максимальное число удалений")
    parser.add_argument("--yes", action="store_true",
                        help="Не спрашивать подтверждение")
    args = parser.parse_args()

    # --execute выключает dry-run
    if args.execute:
        args.dry_run = False

    asyncio.run(main(args))
