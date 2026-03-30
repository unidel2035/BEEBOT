"""InspectFSM — «Осмотр улья» диагностический квест."""
import logging
from typing import Optional

from aiogram import Router, Bot, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.agents.inspector import InspectorAgent, InspectFSM
from src.routers._state import _user_styles

logger = logging.getLogger(__name__)
router = Router()

_inspector: Optional[InspectorAgent] = None


def setup_inspect(inspector: InspectorAgent) -> None:
    global _inspector
    _inspector = inspector


def _inspect_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💡 Получить рекомендацию", callback_data="inspect_finish"),
    ]])


@router.message(Command("inspect"))
async def cmd_inspect(message: types.Message, state: FSMContext):
    """Запустить диагностический диалог «Осмотр улья»."""
    current_state = await state.get_state()
    if current_state and current_state.startswith("OrderFSM"):
        await message.answer("Сначала заверши или отмени текущий заказ (/cancel).")
        return

    await state.set_state(InspectFSM.describing_issue)
    await state.update_data(inspect_collected=[])
    await message.answer(
        "🐝 *Осмотр улья* — персональная консультация\n\n"
        "Опиши, что тебя беспокоит или чего хочешь достичь. "
        "Я задам пару уточняющих вопросов и дам точную рекомендацию.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отменить", callback_data="inspect_cancel"),
        ]]),
    )


@router.message(InspectFSM.describing_issue)
async def inspect_got_issue(message: types.Message, state: FSMContext, bot: Bot):
    """Получить описание проблемы → задать 1-й уточняющий вопрос."""
    issue = (message.text or "").strip()
    if len(issue) < 5:
        await message.answer("Расскажи подробнее — хотя бы несколько слов.")
        return

    collected = [issue]
    await state.update_data(inspect_collected=collected)
    await bot.send_chat_action(message.chat.id, "typing")

    question = _inspector.generate_question(collected)
    await state.set_state(InspectFSM.answering_q1)
    await message.answer(question, reply_markup=_inspect_skip_keyboard())


@router.message(InspectFSM.answering_q1)
async def inspect_got_q1(message: types.Message, state: FSMContext, bot: Bot):
    """Получить ответ на 1-й вопрос → задать 2-й."""
    answer = (message.text or "").strip()
    data = await state.get_data()
    collected: list[str] = data.get("inspect_collected", [])
    collected.append(answer)
    await state.update_data(inspect_collected=collected)
    await bot.send_chat_action(message.chat.id, "typing")

    question = _inspector.generate_question(collected)
    await state.set_state(InspectFSM.answering_q2)
    await message.answer(question, reply_markup=_inspect_skip_keyboard())


@router.message(InspectFSM.answering_q2)
async def inspect_got_q2(message: types.Message, state: FSMContext, bot: Bot):
    """Получить ответ на 2-й вопрос → выдать рекомендацию."""
    answer = (message.text or "").strip()
    data = await state.get_data()
    collected: list[str] = data.get("inspect_collected", [])
    collected.append(answer)
    await state.clear()

    await bot.send_chat_action(message.chat.id, "typing")
    style = _user_styles.get(message.from_user.id)
    recommendation = _inspector.generate_recommendation(collected, style=style)
    await message.answer(
        f"🍯 *Рекомендация*\n\n{recommendation}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Новый осмотр", callback_data="inspect_restart"),
            InlineKeyboardButton(text="📦 Все продукты", callback_data="show_products"),
        ]]),
    )


@router.callback_query(F.data == "inspect_finish")
async def inspect_cb_finish(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Досрочно завершить диалог и получить рекомендацию."""
    data = await state.get_data()
    collected: list[str] = data.get("inspect_collected", [])
    await state.clear()

    if not collected:
        await callback.answer("Сначала опиши проблему.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await bot.send_chat_action(callback.message.chat.id, "typing")
    style = _user_styles.get(callback.from_user.id)
    recommendation = _inspector.generate_recommendation(collected, style=style)
    await callback.message.answer(
        f"🍯 *Рекомендация*\n\n{recommendation}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Новый осмотр", callback_data="inspect_restart"),
            InlineKeyboardButton(text="📦 Все продукты", callback_data="show_products"),
        ]]),
    )


@router.callback_query(F.data == "inspect_cancel")
async def inspect_cb_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отменить диагностику."""
    await state.clear()
    await callback.answer("Осмотр отменён.")
    await callback.message.edit_text("Осмотр отменён. Задай вопрос в любое время.")


@router.callback_query(F.data == "inspect_restart")
async def inspect_cb_restart(callback: types.CallbackQuery, state: FSMContext):
    """Начать осмотр заново."""
    await callback.answer()
    await state.set_state(InspectFSM.describing_issue)
    await state.update_data(inspect_collected=[])
    await callback.message.answer(
        "🐝 *Новый осмотр*\n\nОпиши, что тебя беспокоит.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отменить", callback_data="inspect_cancel"),
        ]]),
    )
