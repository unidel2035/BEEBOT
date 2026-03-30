"""Общее изменяемое состояние для Router-модулей бота.

Все dict/set которые раньше жили в bot.py как module-level globals.
Импортируются по ссылке — изменения видны во всех роутерах.
"""
import asyncio
from typing import Optional, Any

# «Голос Улья» — стиль ответов, выбранный пользователем (user_id → style_id)
_user_styles: dict[int, str] = {}

# Пользователи в режиме «Ассистент пчеловода»
_admin_mode_users: set[int] = set()

# Текущий вид для каждого администратора: "admin" | "user" | "worker"
_admin_view_mode: dict[int, str] = {}

# CRM snapshot — кэш заказов с позициями (устанавливается из main())
_crm_snapshot: Optional[Any] = None

# Хранилище задач таймаута диалога заказа (user_id → asyncio.Task)
_timeout_lock = asyncio.Lock()
_timeout_tasks: dict[int, asyncio.Task] = {}
