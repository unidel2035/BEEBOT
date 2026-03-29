# BEEBOT — Архитектурные диаграммы

> **Версия:** 29 марта 2026

---

## 1. Общая архитектура системы

```mermaid
graph TB
    subgraph Пользователи
        TG_USER[📱 Подписчики<br/>Telegram]
        WORKER[🏭 Работник склада<br/>Telegram]
        ADMIN[🐝 Пчеловод<br/>Telegram + Веб]
        DEV[👨‍💻 Разработчик<br/>DEVBOT + Claude Code]
    end

    subgraph VPS["VPS 185.233.200.13 (Docker)"]
        BOT[🤖 Telegram-бот<br/>aiogram 3 · 1899 строк]
        WEB_API[🌐 FastAPI<br/>REST API + JWT + SSE]
        WEB_FRONT[💻 Vue 3 PWA<br/>порт 8088]
        TRACKER[⏱ Авто-трекинг<br/>каждые 2 часа]
        UDS_POLL[🔄 UDS Poller<br/>каждые 5 минут]
        CRM_SNAP[📷 CrmSnapshot<br/>кэш каждые 5 мин]
    end

    subgraph Агенты["Агенты (src/agents/)"]
        ORCH[🧠 Оркестратор<br/>LangGraph StateGraph]
        CONSUL[🐝 Консультант<br/>FAISS → LLM]
        LOGIST[📦 Логист<br/>FSM 7 шагов]
        ANALYST[📊 Аналитик<br/>CRM → отчёты]
        INSPECT[🔍 Инспектор<br/>Осмотр улья]
        ADMINCHAT[🤖 Ассистент<br/>LLM + CrmSnapshot]
        WORKER_AG[🏭 WorkerAgent<br/>очередь сборки]
    end

    subgraph KB["База знаний"]
        FAISS[(FAISS<br/>240 чанков)]
        DOCS[📄 PDF / TXT<br/>26 YouTube субтитров]
        MEMORY[(SQLite<br/>Факты пользователей)]
        ONTOLOGY[(Integram<br/>74 симптома + 77 показаний)]
    end

    subgraph External["Внешние сервисы"]
        GROQ[⚡ Groq API<br/>llama-3.3-70b]
        CRM[(Integram CRM<br/>ai2o.ru/bibot)]
        CDEK[🚚 СДЭК API v2]
        POCHTA[📮 Почта России]
        UDS_API[💳 UDS API<br/>система лояльности]
        TG_API[💬 Telegram API]
    end

    subgraph HIVE["Hive (локальная машина)"]
        PROXY[groq-proxy<br/>порт 8990]
        TG_SOCKS[SOCKS5-прокси<br/>порт 9150]
        DEVBOT[🤖 DEVBOT<br/>порт 8091]
        CLAUDE[⚡ Claude Code CLI<br/>executor]
    end

    TG_USER -->|сообщения| TG_API
    WORKER -->|/start очередь| TG_API
    ADMIN -->|/admin /stats| TG_API
    ADMIN -->|веб-панель :8088| WEB_FRONT
    DEV -->|/dev задача| TG_API

    TG_API -->|polling SOCKS5| BOT
    BOT --> ORCH
    BOT --> INSPECT
    BOT --> WORKER_AG
    BOT --> ADMINCHAT
    ADMINCHAT --> CRM_SNAP

    ORCH -->|consult| CONSUL
    ORCH -->|order| LOGIST
    ORCH -->|stats| ANALYST
    ORCH -->|greeting| BOT

    CONSUL --> FAISS
    CONSUL --> GROQ

    LOGIST --> CRM
    LOGIST --> CDEK
    LOGIST --> POCHTA

    ANALYST --> CRM

    WORKER_AG --> CRM

    CRM_SNAP --> CRM

    FAISS --> DOCS
    BOT --> MEMORY
    BOT --> ONTOLOGY

    WEB_FRONT -->|REST/JWT| WEB_API
    WEB_API --> CRM
    WEB_API -->|SSE| WEB_FRONT

    TRACKER --> CRM
    TRACKER --> CDEK
    TRACKER --> POCHTA
    UDS_POLL --> UDS_API
    UDS_POLL --> CRM

    BOT -->|DEVBOT_API_URL| DEVBOT
    DEVBOT --> CLAUDE
    CLAUDE -->|git + deploy| VPS

    BOT -->|SOCKS5| TG_SOCKS
    GROQ -->|groq-proxy:8990| PROXY
    TG_SOCKS -->|SSH -R 9150| VPS
    PROXY -->|SSH -L 8990| VPS
```

---

## 2. Поток запроса через оркестратор

```mermaid
flowchart TD
    A[📱 Сообщение Telegram] --> B{Это FSM-состояние?}
    B -->|Да — LogistFSM| C[LogistAgent FSM<br/>шаг диалога]
    B -->|Да — InspectFSM| D[InspectorAgent FSM<br/>шаг диалога]
    B -->|Нет| E{Режим пользователя?}

    E -->|WORKER| F[WorkerAgent<br/>очередь сборки]
    E -->|ADMIN /admin| G[AdminChatAgent<br/>CrmSnapshot → LLM]
    E -->|Обычный| H[Orchestrator.route]

    H --> I{_fast_classify}
    I -->|greeting/order/edit/track| J[Немедленный результат<br/>без LLM]
    I -->|None| K[_classify_intent<br/>Groq ~5 токенов]

    J --> L{Intent}
    K --> L

    L -->|consult| M[BeebotAgent<br/>FAISS search → LLM]
    L -->|order| N[passthrough →<br/>bot.py запускает FSM]
    L -->|edit| O[passthrough →<br/>bot.py показывает меню]
    L -->|track| P[passthrough →<br/>bot.py ищет трек]
    L -->|stats| Q[AnalystAgent<br/>CRM → отчёт]
    L -->|greeting| R[Приветствие по имени]

    M --> S[Загрузить SQLite факты<br/>+ онтологическую рекомендацию]
    S --> T[LLM ответ в Голосе Улья]
    T --> U[FAQ-счётчик++<br/>extract_fact → SQLite]
    U --> V[📤 Ответ пользователю]

    C --> V
    D --> V
    F --> V
    G --> V
    N --> V
    O --> V
    P --> V
    Q --> V
    R --> V
```

---

## 3. FSM оформления заказа (LogistAgent)

```mermaid
stateDiagram-v2
    [*] --> select_products : /order или intent=order

    select_products --> enter_name : выбраны товары
    select_products --> [*] : /cancel

    enter_name --> enter_phone : введено ФИО
    enter_name --> [*] : /cancel

    enter_phone --> confirm_phone : телефон введён
    confirm_phone --> enter_address : ✅ Верно
    confirm_phone --> enter_phone : ❌ Изменить

    enter_address --> select_delivery : введён адрес
    enter_address --> [*] : /cancel

    select_delivery --> confirm_order : выбран способ (СДЭК/Почта/Самовывоз)
    select_delivery --> [*] : /cancel

    confirm_order --> [*] : ✅ Подтвердить → CRM + уведомление пчеловоду
    confirm_order --> select_products : 🔄 Изменить
    confirm_order --> [*] : ❌ Отменить

    note right of select_delivery
        СДЭК: OAuth2 → тарификация
        Почта: tariff.pochta.ru
        Самовывоз: бесплатно
    end note

    note right of confirm_order
        CRM: create_order() + create_order_items()
        Уведомления:
        - пчеловоду (Notifier.new_order)
        - работникам (notify_workers_new_order)
        - группам (ACTIVE_GROUP_IDS)
    end note
```

---

## 4. Поток UDS → CRM

```mermaid
flowchart TD
    A[UDS Poller старт] --> B[load_existing_from_crm<br/>загрузить UDS-* заказы из CRM]
    B --> C[_initial_sync<br/>cursor-пагинация с 01.01.2024]
    C --> D[Бесконечный polling<br/>каждые 5 мин]

    D --> E[get_transactions limit=50]
    E --> F{is_new?}
    F -->|дубль| D
    F -->|новая| G[sync_uds_transaction]

    G --> H[_get_or_create_client_by_phone<br/>поиск/создание клиента]
    H --> I[_build_order_items<br/>⚠️ по имени товара, не SKU]
    I --> J[create_order source=UDS]
    J --> K{notify?}

    K -->|исторический catch-up| L[Без уведомлений]
    K -->|новый в prod| M[notify_beekeeper<br/>+ notify_workers_new_order<br/>+ ACTIVE_GROUP_IDS]

    M --> N[mark_seen]
    L --> N
    N --> D
```

---

## 5. DEVBOT — жизненный цикл задачи

```mermaid
stateDiagram-v2
    [*] --> IDLE

    IDLE --> ANALYZING : /dev <задача>

    ANALYZING --> CONFIRMING : analyze_task() — Claude API<br/>+ dev_memory + советы
    ANALYZING --> IDLE : ошибка анализа

    CONFIRMING --> EXECUTING : ✅ Выполнить
    CONFIRMING --> ANALYZING : уточнение → пересчёт плана
    CONFIRMING --> IDLE : ❌ Отменить

    EXECUTING --> FEEDBACK : exit_code=0<br/>record_completion() в Integram
    EXECUTING --> IDLE : exit_code≠0 → отчёт об ошибке

    FEEDBACK --> EXECUTING : фидбек → feedback loop
    FEEDBACK --> IDLE : /ok или таймаут 10 мин

    note right of ANALYZING
        analyzer.py:
        Claude API → план изменений
        + оценка сложности
        + риски
    end note

    note right of EXECUTING
        executor.py:
        claude --output-format stream-json
        --model claude-sonnet-4.6
        --append-system-prompt rules
        auto-continue через --resume
    end note

    note right of FEEDBACK
        Память (2 уровня):
        1. Integram DEV_TASKS + DEV_MEMORY
        2. .claude/memory/ файлы
    end note
```

---

## 6. WorkerAgent — поток сборки заказов

```mermaid
flowchart TD
    A[Работник: /start] --> B{WORKER_CHAT_IDS?}
    B -->|не в списке| C[Обычный /start → приветствие]
    B -->|в списке| D[get_worker_queue<br/>статусы: Новый/Подтверждён/В сборке]

    D --> E[build_queue_keyboard<br/>список заказов]
    E --> F[Нажать заказ]

    F --> G[format_order_card<br/>+ build_order_keyboard]
    G --> H{Статус заказа}

    H -->|Новый/Подтверждён| I[Показать состав<br/>кнопка: Взять в работу]
    H -->|В сборке| J[Чеклист позиций<br/>toggle каждой позиции]

    I --> K[update_order_status → В сборке<br/>⚠️ _checked в RAM]
    K --> J

    J --> L{Все позиции отмечены?}
    L -->|Нет| J
    L -->|Да| M[Кнопка: Заказ собран!]

    M --> N[update_order_status → Подтверждён<br/>notify_workers_assembled → пчеловоду]
    N --> D

    subgraph Push-уведомления
        P[Новый заказ из TG/UDS/Веб] --> Q[notify_workers_new_order<br/>все WORKER_CHAT_IDS]
        Q --> R[кнопка Открыть очередь]
    end
```

---

## 7. Инфраструктура: туннели и прокси

```mermaid
graph LR
    subgraph VPS["VPS 185.233.200.13"]
        BOT_DOCKER[beebot container<br/>network_mode: host]
        WEB_DOCKER[beebot-web<br/>:8088]
    end

    subgraph HIVE["Hive (локальная машина)"]
        TG_SOCKS_SVC[tg_socks_proxy.py<br/>SOCKS5 :9150]
        GROQ_PROXY_SVC[groq_proxy.py<br/>HTTP-прокси :8990]
        DEVBOT_SVC[devbot<br/>FastAPI :8091]
    end

    subgraph External["Внешние API"]
        TG_API[Telegram API<br/>api.telegram.org]
        GROQ_API[Groq API<br/>api.groq.com]
    end

    BOT_DOCKER -->|SOCKS5 9150| TG_SOCKS_SVC
    TG_SOCKS_SVC -->|HTTPS| TG_API

    BOT_DOCKER -->|HTTP :8990| GROQ_PROXY_SVC
    GROQ_PROXY_SVC -->|HTTPS| GROQ_API

    BOT_DOCKER -->|HTTP localhost:8091<br/>SSH-туннель| DEVBOT_SVC

    subgraph systemd["systemd (hive)"]
        GROQ_TUNNEL[groq-tunnel.service<br/>SSH -L 8990:VPS -R 9150:hive]
        TG_SOCKS_SVC_SD[tg-socks.service]
        GROQ_PROXY_SD[groq-proxy.service]
    end
```

---

## 8. CRM: схема данных Integram

```mermaid
erDiagram
    CLIENTS {
        int id PK
        string full_name
        string phone
        int telegram_id
        string city
        string address
    }

    ORDERS {
        int id PK
        string number
        int client_id FK
        string status
        string source
        string delivery_method
        float total
        datetime date
        string tracking
        int batch_id FK
    }

    ORDER_ITEMS {
        int id PK
        int order_id FK
        int product_id FK
        int quantity
        float unit_price
    }

    PRODUCTS {
        int id PK
        string name
        float price
        int stock
        string category
        string sku_uds
    }

    STATUS_HISTORY {
        int id PK
        int order_id FK
        string status_from
        string status_to
        datetime date
        string comment
    }

    HEALTH_PROFILE {
        int id PK
        int client_id FK
        string symptom
        string source_text
        datetime date
    }

    DEV_TASKS {
        int id PK
        string description
        string status
        string pr_url
        string sha
        string lessons
    }

    DEV_MEMORY {
        int id PK
        string topic
        string context
        string solution
        string files
        string antipattern
    }

    CLIENTS ||--o{ ORDERS : "размещает"
    ORDERS ||--o{ ORDER_ITEMS : "содержит"
    PRODUCTS ||--o{ ORDER_ITEMS : "включён в"
    ORDERS ||--o{ STATUS_HISTORY : "история"
    CLIENTS ||--o{ HEALTH_PROFILE : "профиль здоровья"
```

---

## 9. Сравнительные таблицы

### 9.1 Агенты: возможности и ограничения

| Агент | Доступ к KB | Доступ к CRM | Интент | Ограничения |
|-------|-------------|--------------|--------|-------------|
| Консультант (Beebot) | ✅ FAISS поиск | ❌ | consult | Только знания из KB |
| Логист | ❌ | ✅ Запись | order | Только FSM-диалог |
| Аналитик | ❌ | ✅ Чтение | stats | Только ADMIN_CHAT_ID |
| Инспектор | ✅ FAISS поиск | ❌ | /inspect | Только через команду |
| Ассистент пчеловода | ❌ | ✅ CrmSnapshot | /admin | Только ADMIN_CHAT_ID |
| WorkerAgent | ❌ | ✅ Чтение+Запись | /start (worker) | Только WORKER_CHAT_IDS |
| DEVBOT | ❌ | ✅ DEV-таблицы | /dev | Только hive, только admin |

### 9.2 Источники заказов и их обработка

| Источник | Как попадает в CRM | Позиции | Клиент | Уведомления |
|----------|-------------------|---------|--------|-------------|
| Telegram-бот (FSM) | LogistAgent.confirm → CRM | ✅ Полные | Telegram ID | Пчеловод + Работники |
| UDS система лояльности | UDSPoller → sync_uds_transaction | ⚠️ По имени (SKU=0) | Телефон (telegram_id=0) | Пчеловод + Работники |
| Веб-панель | POST /api/orders | ✅ Ручной ввод | Выбор из CRM | Пчеловод + Работники |
| WhatsApp/ВК/Instagram | Ручной ввод | Ручной ввод | Ручной ввод | Нет |
| DEVBOT (/dev) | Нет — это задачи разработки | — | — | — |

### 9.3 Способы доставки

| Способ | Расчёт стоимости | Трекинг | Авто-уведомление |
|--------|-----------------|---------|-----------------|
| СДЭК | OAuth2 + tariff API | ✅ По трек-номеру | ✅ Каждые 2 ч |
| Почта России | tariff.pochta.ru | ✅ По трек-номеру | ✅ Каждые 2 ч |
| Самовывоз | 0 ₽ (фиксированно) | ❌ | ❌ |

### 9.4 Права доступа

| Роль | Как определяется | Возможности |
|------|-----------------|------------|
| Пользователь | Любой chat_id | consult, /order, /products, /inspect, /voice, /help |
| Работник | `WORKER_CHAT_IDS` в .env | Очередь сборки (/start), статусы В сборке |
| Администратор | `ADMIN_CHAT_ID` / `ADMIN_IDS` | /admin, /stats, /faq, /yt_check, /yt_update, /status, /orders, /clients |
| Веб-пользователь | JWT (WEB_PASSWORD) | Полная веб-панель |

### 9.5 LLM использование по компонентам

| Компонент | LLM-вызов | Токенов/вызов | Цель |
|-----------|-----------|---------------|------|
| Classify intent | Groq | ~100 | Маршрутизация запроса |
| Консультант | Groq | ~2000 | Ответ в стиле автора |
| AdminChatAgent | Groq | ~4000 | Диалог с пчеловодом |
| Аналитик | Groq | ~3000 | Анализ CRM-статистики |
| DEVBOT Analyzer | Claude API (Sonnet) | ~2000 | Анализ задачи → план |
| DEVBOT Executor | Claude Code CLI | ~20000+ | Реализация задачи |

---

*Связанные документы: [analysis.md](../analysis.md) · [plan.md](../plan.md)*
