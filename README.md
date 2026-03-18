# BEEBOT

**Цифровой помощник пчеловода** — Telegram-бот + веб-панель управления заказами для «Усадьба Дмитровых».

Бот отвечает на вопросы подписчиков в стиле автора блога, принимает заказы, управляет складом и доставкой.

**Telegram:** [@AleksandrDmitrov_BEEBOT](https://t.me/AleksandrDmitrov_BEEBOT)

---

## Возможности

### Telegram-бот
- Консультации по продуктам пчеловодства (гибридный FAISS-поиск + LLM)
- Оформление заказов через диалог (FSM, 7 шагов) с записью в CRM
- Каталог товаров с PDF-инструкциями
- Авто-подстановка данных клиента по Telegram ID
- Валидация телефона (+7/8/9xx)
- История диалога (последние 5 сообщений)
- Аналитика продаж для администратора
- Работа в группах (по @mention или reply)

### Веб-панель (PWA)
- Дашборд с графиками (выручка, заказы, статусы, доставка)
- Управление заказами (список, детали, статусы, трекинг) — с пагинацией и поиском
- Каталог клиентов с историей заказов
- CRUD товаров и управление складом
- Терминал сборки заказов (offline-first, PWA)
- Терминал склада (offline-first, PWA)
- Журнал заказов по месяцам
- Экспорт в CSV (заказы, клиенты, товары)
- SSE-уведомления в реальном времени
- JWT-авторизация, rate limiting

### Доставка
- СДЭК API v2: расчёт стоимости (OAuth2 + tariff)
- Почта России: расчёт стоимости (tariff.pochta.ru)
- Авто-трекинг отправлений (фоновая проверка каждые 2 часа)
- Уведомление клиенту при доставке (Telegram)

### CRM-интеграция (Integram)
- 76 товаров, 285+ клиентов, 326+ заказов
- Синхронизация данных в реальном времени
- UDS-синхронизация (система лояльности)
- 6 статусов заказа: Новый → Подтверждён → В сборке → Отправлен → Доставлен / Отменён

---

## Архитектура

```
Telegram ──→ Оркестратор (LangGraph) ──→ Агенты
                                           ├── Консультант (FAISS → Groq LLM)
                                           ├── Логист (FSM заказов → CRM + доставка)
                                           └── Аналитик (CRM → отчёты)

Веб-панель (Vue 3 + PrimeVue, PWA) ──→ FastAPI ──→ Integram CRM

Groq API ←── groq-proxy (hive) ←── SSH-туннель ←── VPS
```

Подробные Mermaid-диаграммы: [docs/architecture.md](docs/architecture.md)

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

# Собрать базу знаний
python -m src.build_kb

# Запустить бота
python -m src.bot
```

### 4. Тесты

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -x -q
```

---

## Структура проекта

```
BEEBOT/
├── src/
│   ├── bot.py                  # Telegram-бот (aiogram 3): хэндлеры, FSM, startup
│   ├── orchestrator.py         # LangGraph — маршрутизация 6 интентов + история
│   ├── config.py               # Конфигурация из .env
│   ├── models.py               # Pydantic-модели (Order, Client, Product)
│   ├── crm_constants.py        # CRM-константы (статусы, источники, категории)
│   ├── crm_schema.py           # Схема таблиц CRM (ID типов, реквизитов)
│   ├── phone_utils.py          # Валидация телефона (+7/8/9xx)
│   ├── agents/
│   │   ├── beebot.py           # Агент-консультант (FAISS → LLM)
│   │   ├── logist.py           # Агент-логист (FSM, 7 шагов → CRM)
│   │   └── analyst.py          # Агент-аналитик (статистика продаж)
│   ├── knowledge_base.py       # FAISS + стилометрия (70/30) + keyword-буст
│   ├── llm_client.py           # Groq API клиент (retry + backoff)
│   ├── integram_api.py         # CRM REST API (низкоуровневый, auto re-auth)
│   ├── integram_client.py      # CRM обёртка (высокоуровневая)
│   ├── admin.py                # Админ-команды Telegram
│   ├── notifications.py        # Уведомления пчеловоду
│   ├── delivery/
│   │   ├── calculator.py       # Калькулятор доставки (СДЭК + Почта + самовывоз)
│   │   ├── cdek.py             # СДЭК API v2 (OAuth2 + tariff + tracking)
│   │   ├── pochta.py           # Почта России API (tariff + tracking)
│   │   └── tracker.py          # Авто-трекинг (фоновая проверка каждые 2 часа)
│   ├── integrations/
│   │   └── uds.py              # UDS — поллер + синхронизация → CRM
│   ├── web/
│   │   ├── api.py              # FastAPI — REST API (JWT, CRUD, пагинация, SSE, CSV)
│   │   ├── notifications.py    # Уведомления клиентам (статус, трекинг)
│   │   ├── users.py            # Управление пользователями веб-панели
│   │   └── server.py           # Статика + PWA root files
│   ├── pdf_loader.py           # Парсинг PDF
│   ├── youtube_loader.py       # Загрузка субтитров YouTube
│   └── build_kb.py             # Сборка базы знаний (txt + pdf + youtube → FAISS)
├── web/                        # Frontend (Vue 3 + PrimeVue, PWA)
│   ├── src/
│   │   ├── views/              # 11 страниц (Dashboard, Orders, Clients, Products, Packing, Stock, Journal...)
│   │   ├── components/         # UI-компоненты (AppLayout, StatCard, StatusBadge)
│   │   ├── stores/             # Pinia (auth) + offline.js (IndexedDB + sync queue)
│   │   ├── router/             # Vue Router (auth guard)
│   │   ├── api.js              # HTTP-клиент (axios + JWT interceptor)
│   │   └── utils.js            # Утилиты (formatDate, formatMoney)
│   ├── vite.config.js          # Vite + VitePWA plugin
│   └── package.json
├── tests/                      # 284 теста (pytest)
├── data/
│   ├── pdfs/                   # 19 PDF-инструкций
│   ├── texts/                  # 21 текстовый источник
│   ├── subtitles/              # 26 расшифровок YouTube
│   └── processed/              # FAISS-индекс (410 чанков) + метаданные
├── docs/
│   └── architecture.md         # Mermaid-диаграммы всех подсистем
├── systemd/                    # systemd-сервисы для hive (groq-proxy, groq-tunnel)
├── .github/workflows/ci.yml   # CI/CD: lint + тесты + деплой
├── Dockerfile                  # Бот (Python + FAISS + sentence-transformers)
├── Dockerfile.web              # Веб-панель (Node build → Python serve)
├── docker-compose.yml          # 2 сервиса: beebot + beebot-web (8088)
├── deploy.sh                   # Деплой на VPS
├── groq_proxy.py               # Reverse proxy (hive:8990 → api.groq.com)
├── analysis.md                 # Анализ проекта (баги, долг, приоритеты)
├── plan.md                     # План развития (5 фаз)
└── CLAUDE.md                   # Инструкции для AI-ассистента
```

---

## Технологии

| Компонент | Технология |
|-----------|-----------|
| Бот | Python 3, aiogram 3, asyncio |
| Оркестратор | LangGraph (StateGraph) |
| LLM | Groq API (llama-3.3-70b-versatile) |
| Эмбеддинги | sentence-transformers (MiniLM-L12-v2) |
| Векторный поиск | FAISS (IndexFlatIP, cosine similarity) |
| CRM | Integram (ai2o.ru) — REST API через httpx |
| Доставка | СДЭК API v2 (OAuth2), Почта России API |
| Веб-API | FastAPI + uvicorn + SSE + slowapi |
| Frontend | Vue 3, PrimeVue, Vite, PWA |
| Offline | Service Worker + IndexedDB |
| Тесты | pytest + pytest-asyncio (284 теста) |
| CI/CD | GitHub Actions (lint + test + deploy) |
| Деплой | Docker, docker-compose, systemd |

---

## Документация

- [Анализ проекта](analysis.md) — сильные/слабые стороны, конфликты, технический долг
- [План развития](plan.md) — дорожная карта по фазам (5 фаз)
- [Архитектура](docs/architecture.md) — Mermaid-диаграммы, сравнительные таблицы, потоки данных

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

The bot answers subscriber questions in the author's personal style, takes orders, manages inventory and shipping.

## Features

- **Telegram bot**: product consultations (hybrid FAISS search + LLM), order processing (7-step FSM with CRM integration), product catalog with PDF guides, conversation history
- **Web dashboard (PWA)**: revenue charts, order/client/product management with pagination & search, packing & stock terminals (offline-first), CSV export, real-time SSE notifications
- **Shipping**: CDEK API v2 (OAuth2) and Russian Post API — real cost calculation + background auto-tracking
- **CRM integration**: Integram (76 products, 285+ clients, 326+ orders), UDS loyalty system sync
- **Multi-agent architecture**: LangGraph orchestrator with Consultant, Logist, and Analyst agents
- **Testing**: 284 tests, GitHub Actions CI/CD with auto-deploy

## Quick Start

```bash
git clone https://github.com/alekseymavai/BEEBOT.git
cd BEEBOT
cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN, GROQ_API_KEY, INTEGRAM_*
docker compose up -d
```

## Tech Stack

Python 3 / aiogram 3 / LangGraph / Groq API (llama-3.3-70b) / FAISS / FastAPI / Vue 3 / PrimeVue / Docker / GitHub Actions

## Documentation

- [Project Analysis](analysis.md) (Russian) — strengths, weaknesses, conflicts, tech debt
- [Development Plan](plan.md) (Russian) — 5-phase roadmap
- [Architecture Diagrams](docs/architecture.md) — Mermaid diagrams, data flows, comparison tables
