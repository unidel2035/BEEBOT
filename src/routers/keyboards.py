"""Тексты сообщений, константы кнопок и построители клавиатур BEEBOT."""

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from src.config import PDFS_DIR
from src.agents.beebot import (
    INSTRUCTIONS,
    CATEGORY_LABELS as _CATEGORY_LABELS,
    get_top_instruction,
)
from src.llm_client import VOICE_STYLES, DEFAULT_VOICE

# ---------------------------------------------------------------------------
# Тексты сообщений
# ---------------------------------------------------------------------------

WELCOME_MESSAGE = """Привет! Я бот-помощник Александра Дмитрова — пчеловода и автора блога о продуктах пчеловодства.

Задай мне любой вопрос о:
- Продуктах пчеловодства (мёд, перга, прополис, пыльца)
- Рецептах и дозировках
- Пчеловодстве и здоровье

Просто напиши свой вопрос или выбери раздел ниже 👇"""

HELP_MESSAGE = """Как пользоваться ботом:

В личных сообщениях — просто напиши вопрос.

В группе — обратись ко мне по имени или ответь на моё сообщение:
• @AleksandrDmitrov_BEEBOT чем полезна перга?
• Или reply на моё сообщение с вопросом

Примеры вопросов:
- Как принимать настойку прополиса?
- Чем полезна перга?
- Как укрепить иммунитет ребёнка?

/start — начать
/ask — задать вопрос
/help — эта справка
/products — список продуктов с инструкциями
/order — оформить заказ
/voice — сменить стиль ответов (Голос Улья)
/inspect — персональная консультация (Осмотр улья)
/admin — включить/выключить режим «Ассистент пчеловода» (админ)
/faq — топ частых вопросов (админ)
/yt_check — проверить новые видео на канале (админ)
/yt_update — обновить базу знаний из YouTube (админ)
/yt_comments — скачать комментарии с ответами автора (админ)
/stats [запрос] — аналитика продаж (админ)
/advice — советы пчеловода для консультанта (админ)
/dev <задача> — отправить задачу в DEVBOT (админ)
/orders [статус] — список заказов (админ)
/order <ID> — детали заказа (админ)
/status <ID> <статус> — сменить статус (админ)
/track <ID> <трек> — добавить трек-номер (админ)
/clients — список клиентов (админ)
/stock — каталог товаров (админ)"""

ASK_MESSAGE = "Напишите свой вопрос — я отвечу на основе знаний о продуктах пчеловодства 🐝"
PRODUCTS_MESSAGE = "Выбери продукт, чтобы получить PDF с инструкцией:"
VOICE_MESSAGE = "Голосовые сообщения пока не поддерживаю — напиши вопрос текстом, отвечу сразу 🙂"
VOICE_HIVE_MESSAGE = (
    "🎙️ *Голос Улья* — выбери стиль ответов:\n\n"
    "Это не разные персонажи — это разные грани одного пчеловода."
)

BOT_USERNAME = "AleksandrDmitrov_BEEBOT"

# ---------------------------------------------------------------------------
# Тексты кнопок главного меню
# ---------------------------------------------------------------------------

BTN_ASK        = "💬 Спросить"
BTN_PRODUCTS   = "📦 Продукты"
BTN_ORDER      = "🛒 Заказать"
BTN_INSPECT    = "🔍 Осмотр улья"
BTN_VOICE      = "🎙 Голос Улья"
BTN_HELP       = "❓ Помощь"
BTN_STATS      = "📊 Статистика"
BTN_ADMIN      = "🤖 Ассистент"
BTN_QUEUE      = "📦 Очередь склада"
BTN_VIEW_USER  = "👤 Глазами клиента"
BTN_VIEW_WORK  = "👷 Глазами работника"
BTN_BACK_ADMIN = "🔙 Режим Админа"
BTN_REFRESH    = "🔄 Обновить CRM"

ALL_MENU_BTNS = {
    BTN_ASK, BTN_PRODUCTS, BTN_ORDER, BTN_INSPECT, BTN_VOICE, BTN_HELP,
    BTN_STATS, BTN_ADMIN, BTN_QUEUE, BTN_VIEW_USER, BTN_VIEW_WORK,
    BTN_BACK_ADMIN, BTN_REFRESH,
}

# ---------------------------------------------------------------------------
# Построители клавиатур
# ---------------------------------------------------------------------------


def build_main_keyboard(is_admin: bool = False, view: str = "admin") -> ReplyKeyboardMarkup:
    """Постоянная нижняя клавиатура.

    view="admin"  — полный режим администратора
    view="user"   — вид глазами клиента (+ кнопка возврата)
    view="worker" — вид глазами работника (только кнопка возврата)
    """
    if view == "user":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text=BTN_ASK), KeyboardButton(text=BTN_PRODUCTS), KeyboardButton(text=BTN_ORDER)],
            [KeyboardButton(text=BTN_INSPECT), KeyboardButton(text=BTN_VOICE), KeyboardButton(text=BTN_HELP)],
            [KeyboardButton(text=BTN_BACK_ADMIN)],
        ], resize_keyboard=True)

    if view == "worker":
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text=BTN_BACK_ADMIN)],
        ], resize_keyboard=True)

    # view == "admin"
    rows = [
        [KeyboardButton(text=BTN_ASK), KeyboardButton(text=BTN_PRODUCTS), KeyboardButton(text=BTN_ORDER)],
        [KeyboardButton(text=BTN_INSPECT), KeyboardButton(text=BTN_VOICE), KeyboardButton(text=BTN_HELP)],
        [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_ADMIN), KeyboardButton(text=BTN_QUEUE)],
        [KeyboardButton(text=BTN_VIEW_USER), KeyboardButton(text=BTN_VIEW_WORK), KeyboardButton(text=BTN_REFRESH)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def build_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📦 Все продукты", callback_data="show_products"),
        InlineKeyboardButton(text="❓ Как пользоваться", callback_data="show_help"),
    ]])


def build_back_to_products_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📦 Все продукты", callback_data="show_products"),
    ]])


def build_products_keyboard() -> InlineKeyboardMarkup:
    rows = []
    current_cat = None
    cat_buttons = []

    for i, (stem, name, fname, cat) in enumerate(INSTRUCTIONS):
        if not (PDFS_DIR / fname).exists():
            continue
        if cat != current_cat:
            if cat_buttons:
                rows += [cat_buttons[j:j+2] for j in range(0, len(cat_buttons), 2)]
            rows.append([InlineKeyboardButton(
                text=_CATEGORY_LABELS.get(cat, cat),
                callback_data="noop",
            )])
            cat_buttons = []
            current_cat = cat
        cat_buttons.append(InlineKeyboardButton(text=name, callback_data=f"doc:{i}"))

    if cat_buttons:
        rows += [cat_buttons[j:j+2] for j in range(0, len(cat_buttons), 2)]

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_instruction_keyboard(chunks: list[dict]) -> InlineKeyboardMarkup:
    result = get_top_instruction(chunks)
    if result is None:
        return build_back_to_products_keyboard()

    idx, name, filename = result
    if not (PDFS_DIR / filename).exists():
        return build_back_to_products_keyboard()

    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"📄 {name}", callback_data=f"doc:{idx}"),
        InlineKeyboardButton(text="📦 Все продукты", callback_data="show_products"),
    ]])


def build_voice_keyboard(current_style: str) -> InlineKeyboardMarkup:
    rows = []
    for sid, sdata in VOICE_STYLES.items():
        check = "✅ " if sid == current_style else ""
        label = f"{check}{sdata['emoji']} {sdata['name']} — {sdata['desc']}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"voice_style:{sid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
