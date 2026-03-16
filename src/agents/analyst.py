"""Агент «Аналитик» — статистика продаж и рекомендации по фасовке.

Анализирует историю заказов из Integram CRM, формирует отчёты:
- Заказы за период (неделя / месяц / произвольный)
- Топ продуктов по количеству и выручке
- Рекомендации по фасовке (что готовить в первую очередь)
- Клиентская аналитика (новые, повторные)
- Разбивка по способам доставки и источникам

Доступен только пользователям с ADMIN_CHAT_ID.
LLM парсит свободный текст в структурированный запрос.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Системный промпт для LLM-парсинга запроса
# ---------------------------------------------------------------------------

_PARSE_SYSTEM = (
    "Ты классификатор аналитических запросов. "
    "По тексту пользователя верни одну строку в формате:\n"
    "  period=<week|month|all>  — период анализа\n"
    "  report=<orders|top|packaging|clients|delivery|sources|summary>  — тип отчёта\n\n"
    "Правила:\n"
    "  week  — 'неделю', 'за 7 дней', 'на этой неделе'\n"
    "  month — 'месяц', 'март', 'за 30 дней', 'в этом месяце'\n"
    "  all   — 'всё время', 'за всё', без явного периода\n"
    "  orders    — сколько заказов, выручка, количество\n"
    "  top       — топ товаров, что продаётся лучше\n"
    "  packaging — что фасовать, что готовить, что запасти\n"
    "  clients   — клиенты, новые, повторные, постоянные\n"
    "  delivery  — способы доставки, СДЭК, Почта\n"
    "  sources   — откуда заказы, источники, каналы, Telegram, UDS\n"
    "  summary   — общая статистика или любой другой запрос\n\n"
    "Ответь ТОЛЬКО двумя параметрами через пробел, например: period=week report=top"
)

_VALID_REPORTS = {"orders", "top", "packaging", "clients", "delivery", "sources", "summary"}


def _parse_analyst_query(groq_client, model: str, query: str) -> tuple[str, str]:
    """Распознать период и тип отчёта из свободного текста через LLM."""
    try:
        resp = groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _PARSE_SYSTEM},
                {"role": "user", "content": query},
            ],
            max_tokens=20,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        period = "all"
        report = "summary"
        for part in raw.split():
            if part.startswith("period="):
                val = part.split("=", 1)[1]
                if val in ("week", "month", "all"):
                    period = val
            elif part.startswith("report="):
                val = part.split("=", 1)[1]
                if val in _VALID_REPORTS:
                    report = val
        return period, report
    except Exception as e:
        logger.warning("LLM-парсинг аналитического запроса не удался: %s", e)
        return "all", "summary"


# ---------------------------------------------------------------------------
# Форматирование отчётов (Telegram Markdown)
# ---------------------------------------------------------------------------


def _period_label(period: str) -> str:
    labels = {"week": "за неделю", "month": "за месяц", "all": "за всё время"}
    return labels.get(period, period)


def format_orders_report(orders: list, period: str) -> str:
    """Отчёт: количество заказов и общая выручка за период."""
    label = _period_label(period)
    if not orders:
        return f"📊 *Заказы {label}:* нет данных."

    total_revenue = sum((o.total or 0.0) for o in orders)
    avg_order = total_revenue / len(orders) if orders else 0
    statuses: Counter = Counter(o.status for o in orders)
    status_lines = "\n".join(f"  • {s}: {c}" for s, c in statuses.most_common())

    lines = [
        f"📊 *Заказы {label}:*\n",
        f"Всего заказов: *{len(orders)}*",
        f"Выручка: *{total_revenue:,.0f} ₽*",
        f"Средний чек: *{avg_order:,.0f} ₽*\n",
        "*По статусам:*",
        status_lines,
    ]
    return "\n".join(lines)


def format_top_products_report(
    orders: list, items_by_order: dict, period: str, top_n: int = 10,
) -> str:
    """Отчёт: топ товаров по количеству и выручке."""
    label = _period_label(period)
    if not orders:
        return f"🏆 *Топ товаров {label}:* нет данных."

    qty_counter: Counter = Counter()
    revenue_counter: defaultdict[str, float] = defaultdict(float)

    for order in orders:
        items = items_by_order.get(order.id, [])
        for item in items:
            name = item.product_name or f"Товар #{item.product_id}"
            qty_counter[name] += item.quantity
            revenue_counter[name] += item.total

    if not qty_counter:
        return f"🏆 *Топ товаров {label}:* нет позиций в заказах."

    total_items = sum(qty_counter.values())
    total_rev = sum(revenue_counter.values())

    lines = [
        f"🏆 *Топ товаров {label}:*",
        f"Всего позиций: {total_items} шт., выручка: {total_rev:,.0f} ₽\n",
    ]
    for i, (name, qty) in enumerate(qty_counter.most_common(top_n), start=1):
        rev = revenue_counter[name]
        pct = (qty / total_items * 100) if total_items else 0
        lines.append(f"{i}. {name}\n   {qty} шт. ({pct:.0f}%) — {rev:,.0f} ₽")

    return "\n".join(lines)


def format_packaging_report(
    orders: list, items_by_order: dict, period: str, top_n: int = 10,
) -> str:
    """Отчёт: рекомендации по фасовке — что готовить в первую очередь."""
    label = _period_label(period)
    if not orders:
        return f"📦 *Рекомендации по фасовке {label}:* нет данных."

    qty_counter: Counter = Counter()
    for order in orders:
        items = items_by_order.get(order.id, [])
        for item in items:
            name = item.product_name or f"Товар #{item.product_id}"
            qty_counter[name] += item.quantity

    if not qty_counter:
        return f"📦 *Рекомендации по фасовке {label}:* нет позиций."

    lines = [
        f"📦 *Что фасовать {label}:*\n",
        "Приоритет по спросу:\n",
    ]
    for i, (name, qty) in enumerate(qty_counter.most_common(top_n), start=1):
        bar = "█" * min(qty, 20)
        lines.append(f"{i}. {name} — *{qty} шт.* {bar}")

    return "\n".join(lines)


def format_clients_report(orders: list, period: str) -> str:
    """Отчёт: клиентская аналитика."""
    label = _period_label(period)
    if not orders:
        return f"👥 *Клиенты {label}:* нет данных."

    client_orders: defaultdict[int, list] = defaultdict(list)
    client_names: dict[int, str] = {}
    for o in orders:
        if o.client_id:
            client_orders[o.client_id].append(o)
            if o.client_name:
                client_names[o.client_id] = o.client_name

    total_clients = len(client_orders)
    repeat = sum(1 for ords in client_orders.values() if len(ords) > 1)
    single = total_clients - repeat

    # Топ клиентов по выручке
    client_revenue = {
        cid: sum((o.total or 0) for o in ords)
        for cid, ords in client_orders.items()
    }
    top_clients = sorted(client_revenue.items(), key=lambda x: x[1], reverse=True)[:5]

    lines = [
        f"👥 *Клиенты {label}:*\n",
        f"Всего клиентов: *{total_clients}*",
        f"  • Разовые: {single}",
        f"  • Повторные: {repeat}",
    ]
    if repeat:
        lines.append(f"  • Процент повторных: {repeat / total_clients * 100:.0f}%")

    if top_clients:
        lines.append("\n*Топ-5 по выручке:*")
        for i, (cid, rev) in enumerate(top_clients, 1):
            name = client_names.get(cid, f"#{cid}")
            cnt = len(client_orders[cid])
            lines.append(f"{i}. {name} — {rev:,.0f} ₽ ({cnt} заказ.)")

    return "\n".join(lines)


def format_delivery_report(orders: list, period: str) -> str:
    """Отчёт: способы доставки."""
    label = _period_label(period)
    if not orders:
        return f"🚚 *Доставка {label}:* нет данных."

    method_counter: Counter = Counter()
    method_revenue: defaultdict[str, float] = defaultdict(float)
    for o in orders:
        method = o.delivery_method or "Не указан"
        method_counter[method] += 1
        method_revenue[method] += o.total or 0

    total = len(orders)
    lines = [f"🚚 *Способы доставки {label}:*\n"]
    for method, cnt in method_counter.most_common():
        pct = cnt / total * 100 if total else 0
        rev = method_revenue[method]
        lines.append(f"  • {method}: *{cnt}* ({pct:.0f}%) — {rev:,.0f} ₽")

    return "\n".join(lines)


def format_sources_report(orders: list, period: str) -> str:
    """Отчёт: источники заказов."""
    label = _period_label(period)
    if not orders:
        return f"📱 *Источники {label}:* нет данных."

    source_counter: Counter = Counter()
    source_revenue: defaultdict[str, float] = defaultdict(float)
    for o in orders:
        source = o.source or "Не указан"
        source_counter[source] += 1
        source_revenue[source] += o.total or 0

    total = len(orders)
    lines = [f"📱 *Источники заказов {label}:*\n"]
    for source, cnt in source_counter.most_common():
        pct = cnt / total * 100 if total else 0
        rev = source_revenue[source]
        lines.append(f"  • {source}: *{cnt}* ({pct:.0f}%) — {rev:,.0f} ₽")

    return "\n".join(lines)


def format_summary_report(orders: list, items_by_order: dict, period: str) -> str:
    """Сводный отчёт: заказы + топ 5 товаров + клиенты."""
    orders_part = format_orders_report(orders, period)
    top_part = format_top_products_report(orders, items_by_order, period, top_n=5)
    clients_part = format_clients_report(orders, period)
    delivery_part = format_delivery_report(orders, period)
    return "\n\n".join([orders_part, top_part, clients_part, delivery_part])


# ---------------------------------------------------------------------------
# Главный класс агента
# ---------------------------------------------------------------------------


class AnalystAgent:
    """Агент для аналитики продаж и рекомендаций по фасовке.

    Доступен только администратору (ADMIN_CHAT_ID).
    LLM (Groq) парсит свободный текст в структурированный запрос.
    """

    def __init__(self, integram_client=None, groq_client=None, groq_model: str = ""):
        self._crm = integram_client
        self._groq = groq_client
        self._model = groq_model

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    async def handle_query(self, query: str) -> str:
        """Обработать свободный текстовый запрос от администратора."""
        period, report_type = self._classify_query(query)
        orders = await self._fetch_orders(period)

        # Загрузить позиции для отчётов по товарам
        items_by_order: dict = {}
        if report_type in ("top", "packaging", "summary") and self._crm:
            items_by_order = await self._fetch_items(orders)

        return self._build_report(orders, items_by_order, period, report_type)

    async def get_sales_summary(self, period: str = "all") -> dict:
        """Получить сводку продаж за период."""
        orders = await self._fetch_orders(period)
        total_revenue = sum((o.total or 0.0) for o in orders)

        items_by_order = {}
        if self._crm:
            items_by_order = await self._fetch_items(orders)

        qty_counter: Counter = Counter()
        for order in orders:
            for item in items_by_order.get(order.id, []):
                name = item.product_name or f"Товар #{item.product_id}"
                qty_counter[name] += item.quantity

        return {
            "total_orders": len(orders),
            "total_revenue": total_revenue,
            "top_products": qty_counter.most_common(5),
            "period": period,
        }

    async def get_packaging_recommendations(self, period: str = "month") -> list[dict]:
        """Получить рекомендации по фасовке."""
        orders = await self._fetch_orders(period)
        items_by_order = {}
        if self._crm:
            items_by_order = await self._fetch_items(orders)

        qty_counter: Counter = Counter()
        for order in orders:
            for item in items_by_order.get(order.id, []):
                name = item.product_name or f"Товар #{item.product_id}"
                qty_counter[name] += item.quantity

        return [
            {"name": name, "quantity": qty}
            for name, qty in qty_counter.most_common()
        ]

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _classify_query(self, query: str) -> tuple[str, str]:
        """Распознать период и тип отчёта."""
        if self._groq and self._model:
            return _parse_analyst_query(self._groq, self._model, query)
        return _keyword_classify(query)

    async def _fetch_orders(self, period: str) -> list:
        """Загрузить заказы из CRM с фильтрацией по дате."""
        if not self._crm:
            logger.info("CRM недоступна — аналитика без данных.")
            return []

        try:
            all_orders = await self._crm.get_orders()
        except Exception as e:
            logger.error("Не удалось загрузить заказы: %s", e)
            return []

        return _filter_by_period(all_orders, period)

    async def _fetch_items(self, orders: list) -> dict:
        """Загрузить позиции для списка заказов.

        Returns:
            {order_id: [OrderItem, ...]}
        """
        if not self._crm or not orders:
            return {}

        try:
            # Загружаем все позиции одним запросом
            all_items = await self._crm.get_order_items_bulk()
        except AttributeError:
            # Fallback: загрузка по одному заказу
            result = {}
            for order in orders:
                try:
                    items = await self._crm.get_order_items(order.id)
                    if items:
                        result[order.id] = items
                except Exception:
                    pass
            return result
        except Exception as e:
            logger.warning("Не удалось загрузить позиции: %s", e)
            return {}

        # Группировать по order_id
        result: defaultdict[int, list] = defaultdict(list)
        for item in all_items:
            result[item.order_id].append(item)
        return dict(result)

    def _build_report(
        self, orders: list, items_by_order: dict, period: str, report_type: str,
    ) -> str:
        """Сформировать текстовый отчёт нужного типа."""
        if report_type == "orders":
            return format_orders_report(orders, period)
        elif report_type == "top":
            return format_top_products_report(orders, items_by_order, period)
        elif report_type == "packaging":
            return format_packaging_report(orders, items_by_order, period)
        elif report_type == "clients":
            return format_clients_report(orders, period)
        elif report_type == "delivery":
            return format_delivery_report(orders, period)
        elif report_type == "sources":
            return format_sources_report(orders, period)
        else:
            return format_summary_report(orders, items_by_order, period)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _keyword_classify(query: str) -> tuple[str, str]:
    """Keyword-классификатор как fallback когда LLM недоступен."""
    q = query.lower()

    # Период
    if any(w in q for w in ("неделю", "неделя", "7 дней", "на этой неделе")):
        period = "week"
    elif any(w in q for w in ("месяц", "30 дней", "в этом месяце",
                               "январ", "феврал", "март", "апрел", "май", "июн",
                               "июл", "август", "сентябр", "октябр", "ноябр", "декабр")):
        period = "month"
    else:
        period = "all"

    # Тип отчёта
    if any(w in q for w in ("фасов", "готовить", "упаковат", "запас")):
        report = "packaging"
    elif any(w in q for w in ("топ", "лучш", "популярн", "продаётся", "продается")):
        report = "top"
    elif any(w in q for w in ("сколько заказов", "количество заказов", "заказов за")):
        report = "orders"
    elif any(w in q for w in ("клиент", "покупател", "повтор", "постоянн")):
        report = "clients"
    elif any(w in q for w in ("доставк", "сдэк", "почт", "самовывоз")):
        report = "delivery"
    elif any(w in q for w in ("источник", "канал", "откуда", "telegram", "uds")):
        report = "sources"
    else:
        report = "summary"

    return period, report


def _filter_by_period(orders: list, period: str) -> list:
    """Отфильтровать заказы по периоду (week / month / all)."""
    if period == "all":
        return orders

    now = datetime.now()
    if period == "week":
        cutoff = now - timedelta(days=7)
    else:  # month
        cutoff = now - timedelta(days=30)

    filtered = []
    for order in orders:
        try:
            order_date = order.date if isinstance(order.date, datetime) else datetime.fromisoformat(str(order.date))
            if order_date >= cutoff:
                filtered.append(order)
        except Exception:
            filtered.append(order)  # при ошибке парсинга — включаем

    return filtered
