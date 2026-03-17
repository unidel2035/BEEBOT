# BEEBOT — Инструкция для Claude

## Что это за проект

**BEEBOT** — Telegram-помощник + веб-панель управления заказами для «Усадьба Дмитровых». Это **цифровой двойник пчеловода** — отвечает на вопросы подписчиков, принимает заказы, управляет складом и доставкой.

Проект создаётся на стыке вековых традиций пчеловодства и современных AI-технологий.

**Целевая аудитория:** подписчики блога Александра Дмитрова, покупатели продуктов пчеловодства.

**Бот в Telegram:** @AleksandrDmitrov_BEEBOT

## Текущие возможности (production)

### 1. База знаний «Пасека»
Гибридная система поиска (FAISS), объединяющая:
- **PDF-инструкции** — 19 документов по прополису, перге, ПЖВМ, гомогенату и др.
- **Тексты** — 21 файл (очищенные выдержки из PDF)
- **Субтитры YouTube** — расшифровки 26 видео с канала @a.dmitrov
- **Стилометрия** — анализ стиля автора (70% семантика + 30% стилометрия)
- **Keyword-буст** — прямое попадание в нужный продукт по ключевым словам
- Всего **410 чанков** в индексе

### 2. Telegram-бот
- `/start` — приветствие + кнопки «Все продукты» / «Как пользоваться»
- `/products` — каталог по категориям: 🍯 Продукты, 🌿 Настойки, 📋 Программы здоровья
- `/ask` — приглашение задать вопрос
- Отправка PDF-инструкций по кнопке
- Работа в группах (по @mention или reply)
- Контекстные кнопки после каждого ответа (релевантный PDF + каталог)

### 3. Многоагентная система (LangGraph)
- **Оркестратор** — классифицирует интент (consult / order / delivery / status / stats / chitchat)
- **Консультант (BEEBOT)** — FAISS-поиск → LLM-ответ в стиле автора
- **Логист** — 7-шаговый FSM оформления заказа (товар → ФИО → телефон → адрес → доставка → подтверждение → создание)
- **Аналитик** — статистика продаж, топ товаров (доступ: только ADMIN_CHAT_ID)

### 4. Веб-панель (PWA)
- **Дашборд** — 6 карточек статистики + 4 графика (выручка, заказы, статусы, доставка)
- **Заказы** — список, детали, смена статуса, трекинг, создание нового
- **Клиенты** — список, карточка клиента с историей заказов
- **Товары** — каталог, CRUD, управление остатками
- **Сборка** (PWA терминал) — чеклист сборки заказов на пасеке, offline-first
- **Склад** (PWA терминал) — учёт остатков, +/− кнопки, алерты при низком запасе, offline-first
- **Журнал** — заказы по месяцам
- JWT-авторизация, PrimeVue UI

### 5. CRM-интеграция (Integram)
- База данных: `bibot` на ai2o.ru
- 76 товаров, 285+ клиентов, 326+ заказов
- Таблицы: Товары, Клиенты, Заказы, Позиции заказа
- Справочники: Категории (8), Источники (6), Статусы (6), Способы доставки (3)
- Жизненный цикл заказа: Новый → Подтверждён → В сборке → Отправлен → Доставлен (или Отменён)

### 6. LLM-генерация ответов
- Модель: `llama-3.3-70b-versatile` через Groq API
- Системный промпт: стиль Александра Дмитрова (дружелюбный, практичный, русскоязычный)
- Защита от галлюцинаций: ответы строго на основе контекста из базы знаний
- Retry-логика (3 попытки с backoff)

## Технологический стек

| Компонент | Технология |
|-----------|-----------|
| Язык | Python 3, asyncio |
| Telegram | aiogram 3 |
| Оркестратор | LangGraph (StateGraph) |
| LLM | Groq API (llama-3.3-70b-versatile) |
| Эмбеддинги | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) |
| Векторный поиск | FAISS (IndexFlatIP, cosine similarity) |
| Чанкинг | langchain-text-splitters (RecursiveCharacterTextSplitter) |
| CRM | Integram (ai2o.ru/bibot) — REST API через httpx |
| Веб-API | FastAPI + uvicorn |
| Frontend | Vue 3, PrimeVue, Vite, PWA (vite-plugin-pwa) |
| Offline | Service Worker + IndexedDB (кэш + sync queue) |
| Валидация | Pydantic 2 |
| PDF-парсинг | PyPDF2 |
| YouTube | youtube-transcript-api, yt-dlp |
| Инфраструктура | Docker, docker-compose, systemd |
| VPS | 185.233.200.13, SSH-туннель для Groq API |

## Структура проекта

```
BEEBOT/
├── src/
│   ├── bot.py                  # Telegram-бот (aiogram 3): хэндлеры, UI, inline-кнопки
│   ├── orchestrator.py         # LangGraph — маршрутизация интентов (6 типов)
│   ├── config.py               # Конфигурация из .env
│   ├── agents/
│   │   ├── beebot.py           # Агент-консультант (FAISS → LLM)
│   │   ├── logist.py           # Агент-логист (FSM заказов, 7 шагов)
│   │   └── analyst.py          # Агент-аналитик (статистика продаж)
│   ├── knowledge_base.py       # FAISS + стилометрия, гибридный поиск
│   ├── llm_client.py           # Groq API клиент, системный промпт
│   ├── integram_api.py         # CRM REST API клиент (низкоуровневый)
│   ├── integram_client.py      # CRM обёртка (высокоуровневая)
│   ├── crm_schema.py           # Схема таблиц CRM (ID типов, реквизитов)
│   ├── models.py               # Pydantic-модели (Order, Client, Product)
│   ├── admin.py                # Админ-команды Telegram
│   ├── notifications.py        # Уведомления пчеловоду
│   ├── delivery/
│   │   ├── calculator.py       # Калькулятор стоимости доставки
│   │   ├── cdek.py             # СДЭК API
│   │   └── pochta.py           # Почта России API
│   ├── integrations/
│   │   └── uds.py              # UDS (система лояльности)
│   ├── web/
│   │   ├── api.py              # FastAPI — REST API (JWT, CRUD, дашборд)
│   │   └── server.py           # Статика + PWA root files
│   ├── pdf_loader.py           # Извлечение текста из PDF
│   ├── youtube_loader.py       # Загрузка субтитров YouTube
│   └── build_kb.py             # Сборка базы знаний (txt → pdf → youtube → FAISS)
├── web/                        # Frontend (Vue 3 + PrimeVue)
│   ├── src/
│   │   ├── views/              # 11 страниц (Dashboard, Orders, Clients, Products, Packing, Stock, Journal...)
│   │   ├── components/         # UI-компоненты (AppLayout, StatCard, StatusBadge)
│   │   ├── stores/             # Pinia (auth) + offline.js (IndexedDB)
│   │   ├── router/             # Vue Router (auth guard)
│   │   ├── api.js              # HTTP-клиент (axios + JWT interceptor)
│   │   └── utils.js            # Утилиты (formatDate, formatMoney)
│   ├── vite.config.js          # Vite + VitePWA plugin
│   └── package.json
├── data/
│   ├── pdfs/                   # 19 PDF-инструкций
│   ├── texts/                  # 21 текстовый источник
│   ├── subtitles/              # 26 расшифровок YouTube
│   └── processed/
│       ├── index.faiss         # FAISS-индекс (410 чанков)
│       └── chunks.json         # Метаданные чанков
├── docs/
│   └── architecture.md         # Mermaid-диаграммы архитектуры
├── systemd/
│   ├── groq-proxy.service      # Автозапуск reverse proxy для Groq на hive
│   ├── groq-tunnel.service     # SSH-туннель VPS↔hive (порт 8990)
│   └── install-hive-services.sh
├── Dockerfile                  # Бот (Python + FAISS + sentence-transformers)
├── Dockerfile.web              # Веб-панель (Node build → Python serve)
├── docker-compose.yml          # 2 сервиса: beebot (host) + beebot-web (8088:8080)
├── deploy.sh                   # Деплой на VPS
├── groq_proxy.py               # Reverse proxy (hive:8990 → api.groq.com)
├── requirements.txt            # Зависимости Python
├── analysis.md                 # Анализ проекта (баги, долг, приоритеты)
├── plan.md                     # План развития (4 фазы)
├── .env                        # Секреты (НЕ в git)
└── .env.example
```

## Архитектура

```
Telegram → aiogram бот (VPS Docker, network_mode: host)
  → Оркестратор (LangGraph) → classify intent
  → Агент Консультант → FAISS (семантика 70% + стилометрия 30%)
  → SSH-туннель (VPS:8990 → hive:8990) ← systemd, auto-restart
  → Groq Proxy (hive, порт 8990)       ← systemd, auto-restart
  → Groq API (llama-3.3-70b-versatile)
  → Ответ в стиле Александра Дмитрова + кнопки с PDF

Веб-панель (Vue 3 + PrimeVue, PWA) → FastAPI (порт 8088)
  → Integram CRM (ai2o.ru/bibot)
  → JWT-авторизация
```

Подробные Mermaid-диаграммы: [docs/architecture.md](docs/architecture.md)

## Инфраструктура и деплой

| Ресурс | Адрес | Детали |
|--------|-------|--------|
| VPS | 185.233.200.13 | ai-agent, SSH-ключ, Docker |
| Веб-панель | http://185.233.200.13:8088 | FastAPI + Vue PWA |
| hive | локальная машина | groq-proxy + groq-tunnel (systemd) |
| SSH-алиас | `beebot-vps` | `ssh beebot-vps` |
| CRM | ai2o.ru/bibot | Integram, база данных `bibot` |
| GitHub upstream | [alekseymavai/BEEBOT](https://github.com/alekseymavai/BEEBOT) | Основной репозиторий |
| GitHub fork | [unidel2035/BEEBOT](https://github.com/unidel2035/BEEBOT) | PR через fork (нет push-доступа к upstream) |

### Быстрые команды
```bash
# Проверить статус
systemctl status groq-proxy groq-tunnel
ssh beebot-vps "docker logs --tail 10 beebot"
ssh beebot-vps "docker logs --tail 10 beebot-web"

# Полный редеплой
ssh beebot-vps "cd /home/ai-agent/BEEBOT && git pull && docker compose up -d --build"

# Пересобрать базу знаний
ssh beebot-vps "docker exec beebot python -m src.build_kb"

# Пересобрать только веб-панель
ssh beebot-vps "cd /home/ai-agent/BEEBOT && docker compose up -d --build beebot-web"
```

## Известные проблемы

Полный анализ: [analysis.md](analysis.md)

### Критические
- **JWT-секрет** — дефолтное значение `dev-secret-change-in-production` в `src/web/api.py`. Нужно сделать обязательной переменной.
- **UDS-интеграция** — `src/integrations/uds.py` вызывает несуществующий `_request()`. Модуль нерабочий.
- **Логист не пишет в CRM** — заказ создаётся только как уведомление, не сохраняется в Integram.

### Серьёзные
- **Дублирование CRM-констант** — lookup ID в 3 местах (integram_api, integram_client, web/api). Нужен единый `crm_constants.py`.
- **Два CRM-клиента** — `integram_api.py` и `integram_client.py` дублируют функционал.
- **CORS `allow_origins=["*"]`** — нужно ограничить до конкретных доменов.

### Известные ограничения
1. **Groq блокирует IP VPS** → решено SSH-туннелем + прокси на hive
2. **YouTube блокирует IP** → субтитры скачаны заранее в `data/subtitles/`
3. **llama-3.3-70b** иногда вставляет иноязычные слова → частично решено промптом
4. **unidel2035** не имеет push-доступа к upstream → только fork + PR
5. **Нет тестов** — ни unit, ни integration, ни e2e
6. **Нет CI/CD** — деплой вручную через `deploy.sh` или `docker compose`

## Документация проекта

| Документ | Описание |
|----------|----------|
| [analysis.md](analysis.md) | Анализ: сильные/слабые стороны, баги, конфликты логик, технический долг |
| [plan.md](plan.md) | План развития: 4 фазы (стабилизация → качество → функции → масштаб) |
| [docs/architecture.md](docs/architecture.md) | Mermaid-диаграммы всех подсистем |
| [README.md](README.md) | Обзор проекта (RU + EN) |

## Для ИИ-ассистента

Если тебя (Claude) запустили в этом репозитории — ты помогаешь с:
1. **Развитием бота** — новые фичи, рефакторинг, багфиксы
2. **Построением системы заказов** — оркестратор, агенты, Integram CRM
3. **Веб-панелью** — новые страницы, графики, PWA-улучшения
4. **Расширением базы знаний** — новые источники данных
5. **Инфраструктурой** — Docker, деплой, мониторинг, CI/CD

### Принципы разработки
- **Русский язык** в интерфейсе, комментариях к коммитам, документации
- **Простота** — пчеловод должен понимать что происходит
- **Надёжность** — бот не должен падать, retry-логика обязательна
- **Стиль автора** — все ответы бота должны звучать как Александр Дмитров
- **Не фантазируй** — бот отвечает только на основе базы знаний
- **Fork workflow** — PR через unidel2035/BEEBOT → alekseymavai/BEEBOT
- **Не дублируй** — перед созданием нового кода проверь, нет ли уже аналога в проекте
- **Актуальность** — при изменении архитектуры обновляй CLAUDE.md, analysis.md и docs/architecture.md
