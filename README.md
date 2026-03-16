# BEEBOT

**Цифровой помощник пчеловода** — Telegram-бот + веб-панель управления заказами для «Усадьба Дмитровых».

Бот отвечает на вопросы подписчиков в стиле автора блога, принимает заказы, управляет складом и доставкой.

**Telegram:** [@AleksandrDmitrov_BEEBOT](https://t.me/AleksandrDmitrov_BEEBOT)

---

## Возможности

### Telegram-бот
- Консультации по продуктам пчеловодства (FAISS + LLM)
- Оформление заказов через диалог (FSM, 7 шагов)
- Каталог товаров с PDF-инструкциями
- Аналитика продаж для администратора
- Работа в группах (по @mention или reply)

### Веб-панель (PWA)
- Дашборд с графиками (выручка, заказы, статусы, доставка)
- Управление заказами (список, детали, статусы, трекинг)
- Каталог клиентов
- CRUD товаров и управление складом
- Терминал сборки заказов (offline-first)
- Терминал склада (offline-first)
- Журнал заказов по месяцам

### CRM-интеграция (Integram)
- 76 товаров, 285+ клиентов, 326+ заказов
- Синхронизация данных в реальном времени
- 6 статусов заказа: Новый → Подтверждён → В сборке → Отправлен → Доставлен / Отменён

---

## Архитектура

```
Telegram ──→ Оркестратор (LangGraph) ──→ Агенты
                                           ├── Консультант (FAISS → Groq LLM)
                                           ├── Логист (FSM заказов → CRM)
                                           └── Аналитик (CRM → отчёты)

Веб-панель (Vue 3 + PrimeVue) ──→ FastAPI ──→ Integram CRM
```

Подробные диаграммы: [docs/architecture.md](docs/architecture.md)

---

## Быстрый старт

### 1. Клонировать и настроить

```bash
git clone https://github.com/alekseymavai/BEEBOT.git
cd BEEBOT
cp .env.example .env
# Отредактировать .env: TELEGRAM_BOT_TOKEN, GROQ_API_KEY, INTEGRAM_*
```

### 2. Docker (рекомендуется)

```bash
docker compose up -d
```

Бот запустится в контейнере `beebot`, веб-панель — на порту 8088.

### 3. Локальная разработка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Собрать базу знаний
python -m src.build_kb

# Запустить бота
python -m src.bot
```

---

## Структура проекта

```
BEEBOT/
├── src/
│   ├── bot.py                  # Telegram-бот (aiogram 3)
│   ├── orchestrator.py         # LangGraph — маршрутизация интентов
│   ├── config.py               # Конфигурация из .env
│   ├── agents/
│   │   ├── beebot.py           # Агент-консультант
│   │   ├── logist.py           # Агент-логист (FSM заказов)
│   │   └── analyst.py          # Агент-аналитик
│   ├── knowledge_base.py       # FAISS + стилометрия, гибридный поиск
│   ├── llm_client.py           # Groq API клиент
│   ├── integram_api.py         # CRM REST API клиент
│   ├── integram_client.py      # CRM высокоуровневая обёртка
│   ├── crm_schema.py           # Схема таблиц CRM
│   ├── models.py               # Pydantic-модели
│   ├── admin.py                # Админ-команды Telegram
│   ├── notifications.py        # Уведомления
│   ├── delivery/
│   │   ├── calculator.py       # Калькулятор доставки
│   │   ├── cdek.py             # СДЭК API
│   │   └── pochta.py           # Почта России API
│   ├── integrations/
│   │   └── uds.py              # UDS (система лояльности)
│   ├── web/
│   │   ├── api.py              # FastAPI — REST API
│   │   └── server.py           # Статика + PWA
│   ├── pdf_loader.py           # Парсинг PDF
│   ├── youtube_loader.py       # Загрузка субтитров YouTube
│   └── build_kb.py             # Сборка базы знаний
├── web/                        # Frontend (Vue 3 + PrimeVue)
│   ├── src/
│   │   ├── views/              # 11 страниц
│   │   ├── components/         # UI-компоненты
│   │   ├── stores/             # Pinia + offline.js
│   │   ├── router/             # Vue Router
│   │   ├── api.js              # HTTP-клиент
│   │   └── utils.js            # Утилиты
│   └── vite.config.js          # Vite + PWA plugin
├── data/
│   ├── pdfs/                   # 19 PDF-инструкций
│   ├── texts/                  # 21 текстовый источник
│   ├── subtitles/              # 26 расшифровок YouTube
│   └── processed/              # FAISS-индекс + метаданные чанков
├── docs/
│   └── architecture.md         # Архитектурные диаграммы (Mermaid)
├── systemd/                    # systemd-сервисы для hive
├── Dockerfile                  # Бот
├── Dockerfile.web              # Веб-панель
├── docker-compose.yml          # Оркестрация контейнеров
├── deploy.sh                   # Деплой на VPS
├── groq_proxy.py               # Прокси для Groq API
├── analysis.md                 # Анализ текущего состояния
├── plan.md                     # План развития
└── CLAUDE.md                   # Инструкции для AI-ассистента
```

---

## Технологии

| Компонент | Технология |
|-----------|-----------|
| Бот | Python 3, aiogram 3, asyncio |
| Оркестратор | LangGraph (state machine) |
| LLM | Groq API (llama-3.3-70b-versatile) |
| Эмбеддинги | sentence-transformers (MiniLM-L12-v2) |
| Векторный поиск | FAISS (IndexFlatIP) |
| CRM | Integram (ai2o.ru) |
| Веб-API | FastAPI + uvicorn |
| Frontend | Vue 3, PrimeVue, Vite, PWA |
| Деплой | Docker, docker-compose, systemd |

---

## Документация

- [Анализ проекта](analysis.md) — сильные/слабые стороны, баги, технический долг
- [План развития](plan.md) — дорожная карта по фазам
- [Архитектура](docs/architecture.md) — Mermaid-диаграммы всех подсистем

---

## Инфраструктура

| Ресурс | Адрес |
|--------|-------|
| VPS | 185.233.200.13 (Docker) |
| Веб-панель | http://185.233.200.13:8088 |
| CRM | ai2o.ru/bibot |
| GitHub (upstream) | [alekseymavai/BEEBOT](https://github.com/alekseymavai/BEEBOT) |

---

# BEEBOT (English)

**Digital beekeeper's assistant** — Telegram bot + web dashboard for order management at "Usadba Dmitrovykh" (Dmitrov's Homestead).

The bot answers subscriber questions in the author's style, takes orders, manages inventory and shipping.

## Features

- **Telegram bot**: product consultations (FAISS + LLM), order processing (7-step FSM), product catalog with PDF guides
- **Web dashboard (PWA)**: revenue charts, order/client/product management, packing terminal, stock terminal (offline-first)
- **CRM integration**: Integram (76 products, 285+ clients, 326+ orders)
- **Multi-agent architecture**: LangGraph orchestrator with Consultant, Logist, and Analyst agents

## Quick Start

```bash
git clone https://github.com/alekseymavai/BEEBOT.git
cd BEEBOT
cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN, GROQ_API_KEY, INTEGRAM_*
docker compose up -d
```

## Tech Stack

Python 3 / aiogram 3 / LangGraph / Groq API (llama-3.3-70b) / FAISS / FastAPI / Vue 3 / PrimeVue / Docker

## Documentation

- [Project Analysis](analysis.md) (Russian)
- [Development Plan](plan.md) (Russian)
- [Architecture Diagrams](docs/architecture.md) (Mermaid)
