# BEEBOT

**Цифровой помощник пчеловода** — Telegram-бот + веб-панель управления заказами для «Усадьба Дмитровых».

Бот отвечает на вопросы подписчиков в стиле автора блога, принимает заказы, управляет складом и доставкой, является личным ассистентом пчеловода с CRM-доступом, а также управляет собственным разработчиком — DEVBOT.

**Telegram:** [@AleksandrDmitrov_BEEBOT](https://t.me/AleksandrDmitrov_BEEBOT)
**Веб-панель:** http://185.233.200.13:8088

---

## Возможности

### Telegram-бот

- Консультации по продуктам пчеловодства — гибридный FAISS (70% семантика + 30% стилометрия + keyword-буст из CRM)
- Оформление заказов через диалог (FSM, 7 шагов) с записью в CRM и расчётом доставки
- Каталог товаров с PDF-инструкциями по каждому продукту
- Автоподстановка данных клиента по Telegram ID (имя, телефон, адрес)
- **«Голос Улья»** — 5 стилей ответов (основатель, наставник, краевед, учёный, молодой)
- **«Осмотр улья»** — диагностический диалог: 3 вопроса → персональная рекомендация
- **«Ассистент пчеловода»** (`/admin`) — личный LLM-помощник с CrmSnapshot (предзагруженный снимок CRM)
- **Режим работника склада** — кнопочная очередь сборки заказов с чеклистом позиций
- Долгосрочная память пользователей (SQLite) + онтологические рекомендации (74 симптома → 77 показаний)
- История диалога (последние 5 сообщений, TTL 30 мин)
- FAQ-коллектор: накапливает частые вопросы, `/faq` показывает топ
- Работа в группах (по @mention или reply)
- Push-уведомления работникам склада при новых заказах

### Веб-панель (PWA, 14 страниц)

- Дашборд с графиками (выручка, заказы, статусы, доставка) + expandable rows с составом
- Управление заказами: список, детали, смена статуса, трекинг, создание, история статусов, чеклист
- Каталог клиентов с историей заказов, объединение дублей
- CRUD товаров и управление складом
- Партии отправки — группировка заказов для массовой отправки
- Терминал сборки заказов (offline-first, PWA)
- Терминал склада: +/− остатков, алерты при низком запасе (offline-first, PWA)
- Журнал заказов по месяцам
- Экспорт в CSV (заказы, клиенты, товары)
- SSE-уведомления в реальном времени
- JWT-авторизация, rate limiting (60 req/min)

### Доставка

- СДЭК API v2: расчёт стоимости (OAuth2 + tariff), трекинг
- Почта России: расчёт стоимости (tariff.pochta.ru), трекинг
- Авто-трекинг отправлений — фоновая проверка каждые 2 часа
- Уведомление клиенту в Telegram при изменении статуса доставки

### CRM-интеграция (Integram bibot)

- 76 товаров · 285+ клиентов · 382+ заказов
- UDS-синхронизация (поллинг каждые 5 мин, cursor-пагинация, catch-up с 01.01.2024, дедупликация)
- 6 статусов заказа: Новый → Подтверждён → В сборке → Отправлен → Доставлен / Отменён
- Keyword-буст: автоматическое расширение словаря KB из каталога CRM
- История статусов заказов (автологирование переходов)
- Профиль здоровья клиентов (74 симптома + 77 показаний к применению)

### DEVBOT — автономный разработчик

- `/dev <задача>` — поставить задачу: анализ → план → подтверждение → Claude Code → deploy
- FSM-диалог: `IDLE → ANALYZING → CONFIRMING → EXECUTING → FEEDBACK`
- Двухуровневая память: файлы Claude Code (`memory/`) + Integram (DEV_TASKS, DEV_MEMORY)
- Советы пчеловода (DEV_ADVICE): операционные знания в контексте задач
- Auto-continue через `--resume <session_id>` при длинных задачах
- `/devstatus`, `/devhistory`, `/devmemory` — управление задачами

---

## Архитектура

```
Пользователи → Telegram API → Бот (aiogram 3, polling)
                                 ├── Оркестратор (LangGraph)
                                 │     ├── Консультант (FAISS → Groq LLM)
                                 │     ├── Логист (FSM 7 шагов → CRM)
                                 │     ├── Аналитик (CRM → отчёты)
                                 │     └── Приветствие
                                 ├── Инспектор (/inspect → FAISS → LLM)
                                 ├── Ассистент (/admin → CrmSnapshot → LLM)
                                 └── WorkerAgent (/start для работников)

Веб-панель (Vue 3 + PrimeVue, PWA) → FastAPI → Integram CRM

Инфраструктура на hive:
  Groq API ← groq-proxy (hive:8990) ← SSH-туннель ← VPS
  Telegram API ← SOCKS5 (hive:9150) ← SSH-туннель ← VPS
  DEVBOT (hive:8091) ← HTTP через SSH-туннель ← /dev команда в боте
```

Подробные диаграммы: [docs/architecture.md](docs/architecture.md)

---

## Быстрый старт

### 1. Клонировать и настроить

```bash
git clone https://github.com/alekseymavai/BEEBOT.git
cd BEEBOT
cp .env.example .env
# Отредактировать .env: TELEGRAM_BOT_TOKEN, GROQ_API_KEY, INTEGRAM_*, WEB_PASSWORD
```

### 2. Docker (рекомендуется)

```bash
docker compose up -d
```

Бот — контейнер `beebot`, веб-панель — порт 8088.

### 3. Собрать базу знаний

```bash
docker exec beebot python -m src.build_kb
```

### 4. Локальная разработка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.build_kb
python -m src.bot
```

### 5. Тесты

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -x -q
```

### 6. DEVBOT (только на hive)

```bash
# Добавить в .env: DEVBOT_TOKEN, ANTHROPIC_API_KEY
python -m src.devbot.bot
# или systemd: systemctl start devbot
```

---

## Структура проекта

```
BEEBOT/
├── src/
│   ├── bot.py                  # Telegram-бот: хэндлеры, FSM, startup (1 899 строк)
│   ├── orchestrator.py         # LangGraph — 6 интентов + история + FAQ
│   ├── config.py               # Конфигурация из .env
│   ├── models.py               # Pydantic-модели (Order, Client, Product, OrderItem)
│   ├── crm_constants.py        # Единый источник CRM ID (таблицы, реквизиты, статусы)
│   ├── crm_schema.py           # Схема таблиц CRM (для документации)
│   ├── crm_snapshot.py         # CrmSnapshot — кэш CRM с TTL
│   ├── phone_utils.py          # Валидация и нормализация телефона
│   ├── memory.py               # SQLite-память пользователей (SQLite)
│   ├── ontology.py             # OntologyCache — симптомы → показания к применению
│   ├── agents/
│   │   ├── beebot.py           # Консультант: FAISS-поиск → LLM-ответ
│   │   ├── logist.py           # Логист: FSM 7 шагов → заказ в CRM
│   │   ├── analyst.py          # Аналитик: статистика + ABC + сезонность + прогноз
│   │   ├── inspector.py        # Инспектор: диагностический диалог
│   │   ├── admin_chat.py       # Ассистент пчеловода: /admin + CrmSnapshot
│   │   └── worker.py           # WorkerAgent: очередь сборки, чеклист
│   ├── devbot/                 # DEVBOT — автономный разработчик (запуск на hive)
│   │   ├── bot.py              # aiogram polling + FastAPI :8091
│   │   ├── fsm.py              # FSM состояний задачи
│   │   ├── analyzer.py         # Claude API → план изменений
│   │   ├── executor.py         # claude CLI (stream-json + auto-continue)
│   │   ├── memory.py           # Integram DEV_TASKS + DEV_MEMORY
│   │   ├── prompts.py          # build_system_prompt + build_user_prompt
│   │   └── config.py           # DEVBOT_TOKEN, DEVBOT_ADMIN_CHAT_ID, DEVBOT_API_PORT
│   ├── knowledge_base.py       # FAISS + стилометрия (70/30) + keyword-буст
│   ├── llm_client.py           # Groq API (retry + backoff + Голос Улья)
│   ├── integram_api.py         # CRM REST API низкоуровневый (auto re-auth)
│   ├── integram_client.py      # CRM обёртка высокоуровневая (Pydantic)
│   ├── admin.py                # Админ-команды Telegram (/orders, /status, /track...)
│   ├── notifications.py        # Notifier: пчеловод + клиенты + работники
│   ├── delivery/
│   │   ├── calculator.py       # Калькулятор (СДЭК + Почта + самовывоз)
│   │   ├── cdek.py             # СДЭК API v2 (OAuth2 + tariff + tracking)
│   │   ├── pochta.py           # Почта России (tariff + tracking)
│   │   └── tracker.py          # Авто-трекинг каждые 2 часа
│   ├── integrations/
│   │   └── uds.py              # UDS: поллер + дедупликация + catch-up → CRM
│   └── web/
│       ├── api.py              # FastAPI: main router + startup (183 строки)
│       ├── routers/            # 9 маршрутных модулей
│       │   ├── auth.py         # /api/login, /api/users
│       │   ├── orders.py       # /api/orders/*
│       │   ├── clients.py      # /api/clients/*
│       │   ├── products.py     # /api/products/*
│       │   ├── dashboard.py    # /api/dashboard/*
│       │   ├── batches.py      # /api/batches/*
│       │   ├── export.py       # CSV-экспорт
│       │   ├── users.py        # Управление пользователями
│       │   └── sse.py          # SSE events
│       ├── notifications.py    # notify_beekeeper_status_change
│       ├── users.py            # Управление пользователями веб-панели
│       └── server.py           # Статика + PWA root
├── web/                        # Frontend (Vue 3 + PrimeVue 4, PWA)
│   └── src/
│       ├── views/              # 14 страниц
│       ├── components/         # AppLayout, StatCard, StatusBadge, OrderItemsTable
│       ├── stores/             # Pinia (auth + offline/IndexedDB)
│       ├── api.js              # axios + JWT interceptor
│       └── utils.js            # formatDate, formatMoney
├── tests/                      # 284 теста (pytest + pytest-asyncio)
├── data/
│   ├── pdfs/                   # 19 PDF-инструкций (прополис, перга, ПЖВМ и др.)
│   ├── texts/                  # 20 текстовых источников
│   ├── subtitles/              # 26 расшифровок YouTube (@a.dmitrov)
│   └── processed/              # FAISS-индекс + chunks.json (240 чанков)
├── docs/
│   └── architecture.md         # Mermaid-диаграммы, блок-схемы, сравнительные таблицы
├── systemd/                    # systemd-сервисы для hive (groq-proxy, groq-tunnel, tg-socks)
├── .github/workflows/ci.yml   # CI/CD: lint (ruff) + тесты + деплой при мерже
├── Dockerfile                  # Бот (Python 3.12-slim + FAISS + fastembed)
├── Dockerfile.web              # Веб-панель (Node build → Python serve)
├── docker-compose.yml          # 2 сервиса: beebot + beebot-web (8088)
├── groq_proxy.py               # Reverse proxy hive:8990 → api.groq.com
├── tg_socks_proxy.py           # SOCKS5-сервер для Telegram API (hive:9150)
├── analysis.md                 # Анализ: сильные/слабые стороны, конфликты
└── plan.md                     # План развития (фазы 8–11)
```

---

## Технологии

| Компонент | Технология |
|-----------|-----------|
| Бот | Python 3.12, aiogram 3.25, asyncio |
| Оркестратор | LangGraph (StateGraph) |
| LLM (бот) | Groq API (llama-3.3-70b-versatile) |
| LLM (DEVBOT) | Anthropic API (claude-sonnet-4-6) |
| Эмбеддинги | fastembed (paraphrase-multilingual-MiniLM-L12-v2) |
| Векторный поиск | FAISS (IndexFlatIP, cosine similarity) |
| Память | SQLite (долгосрочная) + in-memory (диалоги, TTL 30 мин) |
| CRM | Integram (ai2o.ru/bibot) — REST API через httpx |
| Доставка | СДЭК API v2 (OAuth2), Почта России |
| Веб-API | FastAPI + uvicorn + SSE + slowapi |
| Frontend | Vue 3, PrimeVue 4, Vite, PWA (vite-plugin-pwa) |
| Offline | Service Worker + IndexedDB |
| Тесты | pytest + pytest-asyncio (284 теста) |
| CI/CD | GitHub Actions (lint + test + deploy) |
| Деплой | Docker, docker-compose |

---

## Инфраструктура

| Ресурс | Адрес | Детали |
|--------|-------|--------|
| VPS | 185.233.200.13 | Docker, 2 GB RAM + 2 GB swap |
| Веб-панель | http://185.233.200.13:8088 | FastAPI + Vue PWA |
| CRM | ai2o.ru/bibot | Integram, база `bibot` |
| Groq-прокси | hive:8990 | SSH-туннель, systemd groq-proxy.service |
| Telegram-прокси | hive:9150 | SOCKS5, systemd tg-socks.service |
| DEVBOT API | hive:8091 | FastAPI, systemd devbot.service |
| GitHub upstream | [alekseymavai/BEEBOT](https://github.com/alekseymavai/BEEBOT) | PR через fork unidel2035/BEEBOT |

---

## Документация

- [Анализ проекта](analysis.md) — сильные/слабые стороны, логические конфликты, инфраструктура (29.03.2026)
- [План развития](plan.md) — фазы 8–11: качество кода, аналитика, инфраструктура, экосистема
- [Архитектурные диаграммы](docs/architecture.md) — Mermaid-схемы всех подсистем, сравнительные таблицы

---

---

# BEEBOT (English)

**Digital beekeeper's assistant** — Telegram bot + web dashboard for order management at "Usadba Dmitrovykh".

The bot answers subscriber questions in the author's style, processes orders, manages inventory and shipping, serves as a personal AI assistant for the beekeeper with CRM access, and manages its own AI developer — DEVBOT.

**Telegram:** [@AleksandrDmitrov_BEEBOT](https://t.me/AleksandrDmitrov_BEEBOT)
**Web panel:** http://185.233.200.13:8088

## Features

- **Telegram bot:** Product consultations via hybrid FAISS search (70% semantic + 30% stylometric + keyword boost from CRM catalog), 7-step order FSM with CRM integration and shipping cost calculation, PDF product guides, "Voice of the Hive" (5 response styles), "Hive Inspection" diagnostic dialogue, personal LLM assistant (`/admin`) with preloaded CRM snapshot
- **Worker mode:** Button-only order assembly queue with checklist, push notifications on new orders
- **Web dashboard (PWA, 14 pages):** Revenue charts with order items expandable rows, order/client/product management, status history timeline, shipment batches, packing & stock terminals (offline-first), CSV export, real-time SSE, JWT auth
- **Shipping:** CDEK API v2 (OAuth2) and Russian Post — real cost calculation + background auto-tracking every 2 hours
- **CRM:** Integram (76 products, 285+ clients, 382+ orders), UDS loyalty system sync (5-min polling, cursor pagination, catch-up from 01.01.2024)
- **Long-term memory:** SQLite user facts + Integram Health Profile (74 symptoms, 77 indications)
- **DEVBOT:** Autonomous developer agent — /dev task → Claude API analysis → confirmation → Claude Code CLI execution → deploy → dual-layer memory (files + Integram)
- **Multi-agent:** LangGraph orchestrator (6 intents) → Consultant, Logist, Analyst, Inspector, Admin Chat, Worker agents
- **Testing:** 284 tests, GitHub Actions CI/CD with auto-deploy on merge

## Quick Start

```bash
git clone https://github.com/alekseymavai/BEEBOT.git
cd BEEBOT
cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN, GROQ_API_KEY, INTEGRAM_*, WEB_PASSWORD
docker compose up -d
docker exec beebot python -m src.build_kb  # build knowledge base (240 chunks)
```

## Tech Stack

Python 3.12 · aiogram 3 · LangGraph · Groq API (llama-3.3-70b) · Anthropic API (claude-sonnet-4-6) · FAISS · fastembed · SQLite · FastAPI · Vue 3 · PrimeVue 4 · Docker · GitHub Actions

## Documentation

- [Project Analysis (RU)](analysis.md) — strengths, weaknesses, logic conflicts, infrastructure
- [Development Plan (RU)](plan.md) — roadmap phases 8–11
- [Architecture Diagrams](docs/architecture.md) — Mermaid diagrams, data flows, comparison tables
