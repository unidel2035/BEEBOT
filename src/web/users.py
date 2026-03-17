"""Сервис управления пользователями веб-панели.

Пользователи хранятся в таблице «Пользователи» в Integram CRM.
Поля: username (val), password_hash, role, display_name, active.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import bcrypt as _bcrypt

from src.integram_api import (
    IntegramAPI,
    TABLE_USERS,
    REQ_USER_PASSWORD_HASH,
    REQ_USER_ROLE,
    REQ_USER_DISPLAY_NAME,
    REQ_USER_ACTIVE,
    _strip_html,
)

logger = logging.getLogger(__name__)

# Допустимые роли (код → русское название для хранения в CRM)
VALID_ROLES = {"admin", "warehouse"}
_ROLE_TO_CRM = {"admin": "Администратор", "warehouse": "Склад"}
_CRM_TO_ROLE = {v: k for k, v in _ROLE_TO_CRM.items()}


def verify_password(plain: str, hashed: str) -> bool:
    """Проверить пароль по bcrypt-хэшу."""
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def hash_password(plain: str) -> str:
    """Хэшировать пароль через bcrypt."""
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def _parse_user(obj: dict[str, Any]) -> dict[str, Any]:
    """Конвертировать сырой объект Integram в dict пользователя."""
    r = obj["reqs"]
    active_raw = _strip_html(r.get(REQ_USER_ACTIVE, ""))
    crm_role = _strip_html(r.get(REQ_USER_ROLE, ""))
    role = _CRM_TO_ROLE.get(crm_role, "warehouse")
    return {
        "id": obj["id"],
        "username": obj["val"],
        "password_hash": _strip_html(r.get(REQ_USER_PASSWORD_HASH, "")),
        "role": role,
        "display_name": _strip_html(r.get(REQ_USER_DISPLAY_NAME, "")),
        "active": active_raw != "",
    }


async def get_all_users(integram: IntegramAPI) -> list[dict[str, Any]]:
    """Получить всех пользователей (без password_hash в выводе)."""
    raw = await integram.get_all_objects(TABLE_USERS)
    users = []
    for obj in raw:
        u = _parse_user(obj)
        u.pop("password_hash", None)
        users.append(u)
    return users


async def get_user_by_username(
    integram: IntegramAPI, username: str,
) -> Optional[dict[str, Any]]:
    """Найти пользователя по логину. Возвращает dict с password_hash."""
    raw = await integram.get_all_objects(TABLE_USERS)
    for obj in raw:
        if obj["val"] == username:
            return _parse_user(obj)
    return None


async def create_user(
    integram: IntegramAPI,
    username: str,
    password: str,
    role: str,
    display_name: str = "",
) -> int:
    """Создать пользователя. Возвращает ID."""
    if role not in VALID_ROLES:
        raise ValueError(f"Недопустимая роль: {role}")

    existing = await get_user_by_username(integram, username)
    if existing:
        raise ValueError(f"Пользователь '{username}' уже существует")

    reqs = {
        REQ_USER_PASSWORD_HASH: hash_password(password),
        REQ_USER_ROLE: _ROLE_TO_CRM[role],
        REQ_USER_DISPLAY_NAME: display_name or username,
        REQ_USER_ACTIVE: "1",
    }
    user_id = await integram.create_object(TABLE_USERS, username, reqs)
    logger.info("Создан пользователь '%s' (id=%d, role=%s)", username, user_id, role)
    return user_id


async def update_user(
    integram: IntegramAPI,
    user_id: int,
    password: Optional[str] = None,
    role: Optional[str] = None,
    display_name: Optional[str] = None,
    active: Optional[bool] = None,
) -> None:
    """Обновить поля пользователя."""
    reqs: dict[str, str] = {}
    if password:
        reqs[REQ_USER_PASSWORD_HASH] = hash_password(password)
    if role is not None:
        if role not in VALID_ROLES:
            raise ValueError(f"Недопустимая роль: {role}")
        reqs[REQ_USER_ROLE] = _ROLE_TO_CRM[role]
    if display_name is not None:
        reqs[REQ_USER_DISPLAY_NAME] = display_name
    if active is not None:
        reqs[REQ_USER_ACTIVE] = "1" if active else ""
    if reqs:
        await integram.set_requisites(user_id, TABLE_USERS, reqs)


async def delete_user(integram: IntegramAPI, user_id: int) -> None:
    """Деактивировать пользователя (soft delete)."""
    await integram.set_requisites(user_id, TABLE_USERS, {
        REQ_USER_ACTIVE: "",
    })
