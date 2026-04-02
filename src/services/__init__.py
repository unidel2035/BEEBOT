"""Service Layer — единый источник бизнес-логики BEEBOT.

Сервисы не знают про Telegram, FastAPI или Redis.
Они работают с CRM, LLM, KB через инъекцию зависимостей.
"""
