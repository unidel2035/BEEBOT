# BEEBOT

**Цифровой помощник пчеловода** — Telegram-бот + веб-панель управления заказами для «Усадьба Дмитровых».

Telegram: [@AleksandrDmitrov_BEEBOT](https://t.me/AleksandrDmitrov_BEEBOT) · Веб-панель: http://185.233.200.13:8088

---

## Возможности

### Telegram-бот
- `/start`, `/products`, `/help` — главное меню (ReplyKeyboard)
- `/order` — оформление заказа (FSM, 7 шагов: товары → ФИО → телефон → адрес → доставка → подтверждение → CRM)
- `/inspect` — «Осмотр улья»: 3-шаговый диагностический диалог → рекомендация
- `/voice` — выбор «Голоса Улья» (5 стилей: наставник, практик, селекционер, зимовщик, эколог)
- `/admin` — личный ассистент пчеловода + CRM-контекст (только ADMIN_CHAT_ID)
- `/stats [запрос]` — аналитика продаж: ABC, сезонность, прогноз (только ADMIN_CHAT_ID)
- `/dev <задача>` — поставить задачу DEVBOT (только ADMIN_CHAT_ID)
- `/faq` — топ частых вопросов (только ADMIN_CHAT_ID)
- Режим работника — очередь сборки, чеклисты, push-уведомления (WORKER_CHAT_IDS)

### Многоагентная система (LangGraph)
- **Оркестратор** — классификация интента: consult / order / edit / track / stats / greeting
- **Консультант** — FAISS-поиск → LLM в стиле автора (70% семантика + 30% стилометрия)
- **Логист** — 7-шаговый FSM оформления заказа → OrderService → CRM
- **Аналитик** — ABC-анализ, сезонность, прогноз спроса
- **Инспектор** — диагностический диалог «Осмотр улья» (KB без CRM)
- **Ассистент** — /admin: LLM-диалог + CrmSnapshot (кэш 5 мин)
- **Работник** — очередь сборки заказов для WORKER_CHAT_IDS

### Веб-панель (14 страниц, PWA)
- **Дашборд** — 6 карточек + 4 графика + топ-5 товаров + блок «Требуют внимания»
  - Переключатель периода: Сегодня / 7д / 30д / Квартал / Всё время
- **Заказы** — список с поиском/фильтром, инлайн-смена статуса, Канбан с drag & drop, batch-операции
- **Клиенты / Товары / Склад / Партии** — полный CRUD
- **Сборка** — PWA offline чеклист (Service Worker + IndexedDB)
- **Экспорт CSV**, SSE real-time уведомления, JWT-авторизация

### База знаний
- **276 чанков** — 20 текстовых источников + 26 YouTube-расшифровок + 19 PDF
- **Гибридный поиск** — FAISS (IndexFlatIP) + стилометрия + keyword-буст из каталога
- **Онтология** — 74 симптома + 77+ показаний к применению

### CRM-интеграция (Integram)
- **v2 (ai2o.online)** — основная CRM: JWT, 85 товаров, singleflight кэш
- **v1 (ai2o.ru)** — архив: 1924 клиента, 1915 заказов (read-only)
- **UDS-синхронизация** — поллинг каждые 5 мин, catch-up с 01.01.2024, дедупликация
- **Авто-трекинг** — СДЭК + Почта России каждые 2 часа

### DEVBOT — автономный разработчик
- `/dev <задача>` → HTTP POST → DEVBOT API (hive:8091)
- FSM: IDLE → ANALYZING (Claude API) → CONFIRMING → EXECUTING (claude CLI) → FEEDBACK
- Память: Integram DEV_TASKS + DEV_MEMORY + DEV_ADVICE

---

## Технологии

| Компонент | Технология |
|-----------|-----------|
| Язык | Python 3.12 (asyncio) |
| Telegram | aiogram 3.25 |
| Оркестратор | LangGraph (StateGraph) |
| LLM (бот) | Groq API (llama-3.3-70b-versatile) |
| LLM (DEVBOT) | Anthropic API (claude-sonnet-4-6) |
| Эмбеддинги | fastembed (paraphrase-multilingual-MiniLM-L12-v2) |
| Векторный поиск | FAISS (IndexFlatIP, cosine similarity) |
| Память | SQLite (долгосрочная) + RAM dict (диалоги, TTL 30 мин) |
| CRM | Integram v2 (ai2o.online) + v1 архив (ai2o.ru) |
| Веб-API | FastAPI + uvicorn + SSE + slowapi |
| Frontend | Vue 3, PrimeVue 4, Vite, PWA |
| Offline | Service Worker + IndexedDB |
| Валидация | Pydantic 2 |
| Тесты | pytest + pytest-asyncio (39 файлов, 8715 строк) |
| CI/CD | GitHub Actions (ruff + mypy + bandit + pytest + deploy) |
| Инфраструктура | Docker, docker-compose, Redis 7, systemd |
| VPS | 185.233.200.13 (ai-agent, 2 GB RAM + 2 GB swap) |

---

## Структура проекта

```
BEEBOT/
├── src/
│   ├── bot.py                     # Telegram-бот: инициализация, 7 роутеров (196 строк)
│   ├── startup.py                 # create_services() — единая точка инициализации (335 строк)
│   ├── orchestrator.py            # LangGraph: 7 интентов (502 строки)
│   ├── config.py                  # Конфигурация (.env, 114 строк)
│   ├── models.py                  # Pydantic-модели: Order, Client, Product (83 строки)
│   ├── crm_factory.py             # Фабрика: get_crm_client() → v1 или v2
│   ├── crm_constants.py           # ID таблиц и реквизитов v1 CRM
│   ├── crm_snapshot.py            # CrmSnapshot — кэш с TTL 5 мин
│   ├── integram_client.py         # CRM v1 клиент (ai2o.ru, 849 строк)
│   ├── integram_v2_client.py      # CRM v2 клиент (ai2o.online, 1002 строки)
│   ├── integram_v2_constants.py   # ID таблиц и колонок v2 CRM
│   ├── integram_api.py            # Низкоуровневый HTTP-клиент (auto re-auth)
│   ├── knowledge_base.py          # FAISS + стилометрия + keyword-буст (332 строки)
│   ├── llm_client.py              # Groq API + retry + 5 голосов
│   ├── memory.py                  # UserMemory — SQLite факты пользователей
│   ├── ontology.py                # OntologyCache — симптомы → показания
│   ├── shared_context.py          # SharedContextStore — диалог-контекст (TTL 30 мин)
│   ├── gift_protocol.py           # GiftBroker — передача контекста между агентами
│   ├── phone_utils.py             # Валидация телефонов
│   ├── utils.py                   # parse_date(), RU_MONTHS
│   ├── prompts.py                 # Централизованные LLM-промпты
│   ├── agents/
│   │   ├── beebot.py              # Консультант: FAISS → LLM (134 строки)
│   │   ├── logist.py              # Логист: FSM 7 шагов → OrderService (491 строка)
│   │   ├── analyst.py             # Аналитик: ABC, сезонность, прогноз
│   │   ├── inspector.py           # Инспектор: «Осмотр улья» (158 строк)
│   │   ├── admin_chat.py          # Ассистент: /admin + CrmSnapshot (282 строки)
│   │   └── worker.py              # WorkerAgent: очередь сборки (169 строк)
│   ├── routers/                   # 7 Telegram-роутеров
│   │   ├── user.py                # Основной обработчик (StateFilter None)
│   │   ├── bot_admin.py           # Админ-команды: stats, faq, dev, voice
│   │   ├── inspect.py             # InspectFSM
│   │   ├── fsm_order.py           # OrderFSM (7 шагов)
│   │   ├── fsm_edit.py            # Редактирование состава заказа
│   │   ├── worker.py              # Очередь сборки
│   │   └── keyboards.py           # ReplyKeyboard + InlineKeyboard
│   ├── services/
│   │   ├── order_service.py       # OrderService: create/update + уведомления
│   │   └── notification_service.py # NotificationService: Telegram push
│   ├── delivery/                  # СДЭК + Почта России + расчёт + трекинг
│   ├── integrations/
│   │   └── uds.py                 # UDSPoller: каждые 5 мин + catch-up 2024
│   ├── devbot/                    # DEVBOT: autonomous developer
│   └── web/
│       ├── api.py                 # FastAPI: lifespan, 9 роутеров (320 строк)
│       ├── deps.py                # Dependency injection
│       ├── routers/               # auth, orders, clients, products, dashboard...
│       └── server.py              # Раздача Vue dist/ + PWA
├── web/                           # Frontend (Vue 3 + PrimeVue 4, PWA)
│   └── src/
│       ├── views/                 # 14 страниц
│       ├── components/            # AppLayout, StatCard, StatusBadge, OrderItemsTable
│       ├── stores/                # Pinia auth + offline.js (IndexedDB + sync queue)
│       ├── api.js                 # axios + JWT interceptor
│       └── utils.js               # formatDate, formatMoney
├── tests/                         # 39 файлов, 8715 строк
├── data/
│   ├── pdfs/                      # 19 PDF-инструкций
│   ├── texts/                     # 20 текстовых источников
│   ├── subtitles/                 # 26 YouTube-расшифровок
│   └── processed/                 # FAISS-индекс + chunks.json (276 чанков)
├── docs/
│   ├── architecture.md            # 16 Mermaid-диаграмм + таблицы
│   └── memory_architecture.md     # Архитектура памяти агентов (best practices 2025)
├── systemd/                       # systemd-сервисы для hive
├── scripts/                       # Утилиты: cleanup_duplicate_orders.py
├── docker-compose.yml             # Redis 7 + beebot (network_mode: host)
├── Dockerfile / Dockerfile.web
├── .github/workflows/ci.yml       # CI/CD: ruff+mypy+bandit+pytest+deploy
├── groq_proxy.py                  # Reverse proxy hive:8990 → api.groq.com
├── tg_socks_proxy.py              # SOCKS5 hive:9150 → Telegram API
├── uds_proxy.py                   # Reverse proxy hive:8991 → api.uds.app
├── analysis.md                    # Текущий анализ проекта
└── plan.md                        # План развития
```

---

## Запуск

```bash
# Docker (production)
docker compose up -d --build

# Локальная разработка
pip install -r requirements.txt
python -m src.bot           # бот + веб-панель (unified mode)

# Только веб (без Telegram polling)
uvicorn src.web.server:app --port 8088

# Пересобрать базу знаний
python -m src.build_kb
```

### Переменные окружения

```env
# Telegram
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=...
WORKER_CHAT_IDS=...          # через запятую

# LLM
GROQ_API_KEY=...
GROQ_API_BASE=http://localhost:8990   # SSH-туннель через hive

# CRM v2 (основная)
INTEGRAM_V2=true
INTEGRAM_V2_EMAIL=...
INTEGRAM_V2_PASSWORD=...
INTEGRAM_V2_WORKSPACE=alekseymavai

# CRM v1 (архив, read-only)
INTEGRAM_URL=https://ai2o.ru
INTEGRAM_LOGIN=...
INTEGRAM_PASSWORD=...
INTEGRAM_DB=bibot

# Веб-панель
WEB_SECRET_KEY=...
WEB_USERNAME=...
WEB_PASSWORD=...
WEB_CORS_ORIGINS=http://localhost:5173

# Бекап (опционально)
YADISK_TOKEN=...

# UDS-синхронизация (опционально)
UDS_API_KEY=...
UDS_COMPANY_ID=...
```

---

## Тесты

```bash
pytest                                    # все тесты
pytest tests/test_integram_v2_client.py  # CRM v2 (27 тестов)
pytest tests/test_bot.py                 # Telegram роутеры
pytest -k "integram"                     # все CRM-тесты
pytest --cov=src --cov-report=html       # покрытие
```

---

## Деплой

```bash
# После squash-мержа PR → VPS синхронизация
ssh ai-agent@185.233.200.13 "cd /home/ai-agent/BEEBOT && git fetch origin main && git reset --hard origin/main"

# Пересборка с новым кодом
ssh ai-agent@185.233.200.13 "cd /home/ai-agent/BEEBOT && docker compose up -d --build --force-recreate beebot"

# Логи
ssh ai-agent@185.233.200.13 "docker logs --tail 30 beebot"
```

---

## Документация

| Документ | Описание |
|----------|----------|
| [analysis.md](analysis.md) | Анализ: сильные/слабые стороны, конфликты логик, аудит кода |
| [plan.md](plan.md) | План развития: 9 направлений с задачами и приоритетами |
| [docs/architecture.md](docs/architecture.md) | 16 Mermaid-диаграмм: агенты, CRM, деплой, потоки данных |
| [docs/memory_architecture.md](docs/memory_architecture.md) | Архитектура памяти агентов, best practices 2025 |
| [CLAUDE.md](CLAUDE.md) | Инструкция для Claude-ассистента |

---

---

# BEEBOT (English)

**Digital beekeeper assistant** — Telegram bot + web panel for order management at "Usadba Dmitrovykh" (Dmitrov Estate).

**Telegram:** [@AleksandrDmitrov_BEEBOT](https://t.me/AleksandrDmitrov_BEEBOT) · **Web panel:** http://185.233.200.13:8088

## Features

- **Telegram bot** — product consultations, 7-step order FSM, hive inspection, sales analytics, 5 voice styles
- **Multi-agent system** (LangGraph) — 6 agents: consultant, logistician, analyst, inspector, admin assistant, warehouse worker
- **Knowledge base** — 276 chunks (texts + YouTube + PDFs), hybrid search (FAISS + stylometry), ontology 74 symptoms
- **Web panel** (14 pages, PWA) — dashboard with charts, orders (Kanban + drag&drop), clients, products, stock, offline packing
- **Dual CRM** — Integram v2 (ai2o.online, main) + v1 archive (ai2o.ru)
- **Auto-tracking** — CDEK + Russian Post every 2 hours
- **UDS sync** — polling every 5 min, catch-up from 2024
- **DEVBOT** — autonomous developer via /dev (Claude API + CLI)
- **Gift Protocol** — SharedContext between agents (cross-agent memory)

## Tech Stack

```
Python 3.12 | aiogram 3.25 | LangGraph | Groq llama-3.3-70b | FAISS
FastAPI | Vue 3 + PrimeVue 4 | PWA (Service Worker + IndexedDB)
Integram CRM v2 (JWT) | Redis 7 | Docker | GitHub Actions CI/CD
```

## Quick Start

```bash
# Docker
docker compose up -d --build

# Local dev
pip install -r requirements.txt
python -m src.bot
```

## Environment

```env
INTEGRAM_V2=true                         # Use CRM v2 (ai2o.online)
TELEGRAM_BOT_TOKEN=...
GROQ_API_KEY=...
INTEGRAM_V2_EMAIL=...
INTEGRAM_V2_PASSWORD=...
INTEGRAM_V2_WORKSPACE=alekseymavai
```

## Tests

```bash
pytest                                   # all 39 files, 8715 lines
pytest tests/test_integram_v2_client.py  # CRM v2 (27 tests)
```

## Documentation

- [analysis.md](analysis.md) — Project analysis (strengths, weaknesses, logic conflicts, code audit)
- [plan.md](plan.md) — Development roadmap (9 directions, prioritized tasks)
- [docs/architecture.md](docs/architecture.md) — Architecture diagrams (16 Mermaid charts)
- [docs/memory_architecture.md](docs/memory_architecture.md) — Agent memory architecture, 2025 best practices
