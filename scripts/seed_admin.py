"""Создать начального администратора в таблице «Пользователи» Integram CRM.

Использование:
    python -m scripts.seed_admin

Берёт логин/пароль из WEB_USERNAME / WEB_PASSWORD (.env).
Если пользователь уже существует — пропускает.
"""

import asyncio
import os
import sys

# Загрузить .env до импорта src
from dotenv import load_dotenv
load_dotenv()

from src.integram_api import IntegramAPI
from src.web.users import get_user_by_username, create_user


async def main() -> None:
    username = os.getenv("WEB_USERNAME", "admin")
    password = os.getenv("WEB_PASSWORD", "changeme")

    print(f"Создаём администратора '{username}'...")

    integram = IntegramAPI()
    await integram.authenticate()

    try:
        existing = await get_user_by_username(integram, username)
        if existing:
            print(f"Пользователь '{username}' уже существует (id={existing['id']}). Пропускаем.")
            return

        user_id = await create_user(
            integram,
            username=username,
            password=password,
            role="admin",
            display_name="Администратор",
        )
        print(f"Создан администратор '{username}' (id={user_id}).")
    finally:
        await integram.close()


if __name__ == "__main__":
    asyncio.run(main())
