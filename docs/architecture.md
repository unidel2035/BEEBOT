# BEEBOT — Архитектурные диаграммы

> **Версия:** 4 апреля 2026 (обновлено: Backend as Single Entry Point)

---

## 1. Общая архитектура: Backend как единая точка входа

```mermaid
graph TB
    subgraph USERS["Пользователи"]
        U1["Подписчики<br/>(Telegram)"]
        U2["Пчеловод<br/>(Admin)"]
        U3["Работники<br/>(Worker)"]
        U4["Веб-панель<br/>(Браузер)"]
    end

    subgraph UNIFIED["Единый Backend (Docker)"]
        subgraph TRANSPORT["Транспортный слой"]
            HANDLERS["Роутеры aiogram<br/>admin / user / fsm / inspect / worker"]
            API["FastAPI :8088<br/>9 веб-роутеров"]
            VUE["Vue 3 PWA<br/>14 страниц"]
        end

        STARTUP["startup.py<br/>Единая точка<br/>инициализации"]

        subgraph SVC_LAYER["Service Layer"]
            AUTH["AuthService"]
            ORDER_SVC["OrderService"]
            CONSULT["ConsultService"]
            ANALYTICS["AnalyticsService"]
            DASHBOARD["DashboardService"]
            WORKER_SVC["WorkerService"]
            DELIVERY_SVC["DeliveryService"]
            NOTIFY["NotificationService"]
        end

        subgraph CROSS["Cross-cutting"]
            EVENTS["EventEmitter<br/>order.created<br/>order.status_changed"]
            BREAKER["CircuitBreaker<br/>CRM protection"]
            STATE["StateStore<br/>(Redis / fallback)"]
            BG["BackgroundTaskManager<br/>5 задач"]
        end

        BUS["EventBus<br/>(Redis Streams)"]
    end

    subgraph INFRA["Инфраструктура"]
        CRM[("CRM<br/>ai2o.online")]
        REDIS[("Redis<br/>:6379")]
        KB["FAISS<br/>276 чанков"]
        LLM["Groq API<br/>llama-3.3-70b"]
        MEM["SQLite<br/>память"]
    end

    subgraph EXTERNAL["Внешние системы"]
        UDS_API["UDS App"]
        CDEK_A["СДЭК API"]
        POCHTA_A["Почта России"]
    end

    U1 & U2 & U3 --> HANDLERS
    U4 --> VUE --> API

    STARTUP -->|"создаёт"| SVC_LAYER
    STARTUP -->|"создаёт"| CROSS

    HANDLERS --> SVC_LAYER
    API --> SVC_LAYER
    BUS --> SVC_LAYER

    SVC_LAYER --> KB & LLM & MEM & CRM
    EVENTS -->|"SSE bridge"| API
    EVENTS -->|"Redis publish"| BUS
    STATE --> REDIS
    BREAKER -->|"fallback при сбое"| CRM
    BG -->|"polling 5 мин"| UDS_API
    BG -->|"авто-трекинг 2ч"| CDEK_A & POCHTA_A

    style SVC_LAYER fill:#e8f5e9,stroke:#22c55e
    style CROSS fill:#fff8e1,stroke:#f9a825
    style CRM fill:#bbf7d0,stroke:#22c55e
    style EXTERNAL fill:#f3e5f5
    style STARTUP fill:#e3f2fd,stroke:#1976d2
```

---

## 2. Единая инициализация: startup.py

```mermaid
graph TB
    subgraph ENTRY["Точки входа"]
        BOT_ENTRY["src/bot.py<br/>python -m src.bot<br/>(polling)"]
        WEB_ENTRY["src/web/api.py<br/>uvicorn<br/>(lifespan)"]
    end

    STARTUP["src/startup.py<br/>create_services()"]

    subgraph SERVICES["Services (контейнер)"]
        AUTH_S["AuthService"]
        CRM_S["CRM Client<br/>(singleton)"]
        ORDER_S["OrderService"]
        ANALYTICS_S["AnalyticsService"]
        CONSULT_S["ConsultService"]
        WORKER_S["WorkerService"]
        DELIVERY_S["DeliveryService"]
        DASHBOARD_S["DashboardService"]
        STATE_S["StateStore<br/>(Redis)"]
        BG_S["BackgroundTaskManager"]
    end

    subgraph AGENTS["Агенты (тонкие обёртки)"]
        ORCH["Orchestrator"]
        BEEBOT_A["BeebotAgent"]
        ANALYST_A["AnalystAgent"]
        LOGIST_A["LogistAgent"]
        WORKER_A["WorkerAgent"]
        ADMIN_A["AdminChatAgent"]
        INSPECT_A["InspectorAgent"]
    end

    BOT_ENTRY -->|"await create_services()"| STARTUP
    WEB_ENTRY -->|"await create_services()"| STARTUP

    STARTUP -->|"возвращает"| SERVICES
    STARTUP -->|"создаёт"| AGENTS

    WEB_ENTRY -->|"app.state.crm"| CRM_S
    WEB_ENTRY -->|"set_crm_singleton()"| CRM_S

    BOT_ENTRY -->|"setup_routers(svc)"| AGENTS

    style STARTUP fill:#e3f2fd,stroke:#1976d2
    style SERVICES fill:#e8f5e9,stroke:#22c55e
    style AGENTS fill:#fff3e0
```

**Anti-pattern avoided:** «Creating new DB connections or HTTP clients inside each route handler.» Теперь один CRM-клиент на весь процесс.

---

## 3. Service Layer: архитектура слоёв

```mermaid
graph TB
    subgraph TRANSPORT["Транспортный слой (вход)"]
        TG["Telegram<br/>bot.py + 5 роутеров"]
        WEB_T["FastAPI<br/>api.py + 9 роутеров"]
        REDIS_BUS["Redis Streams<br/>bus_handlers.py"]
    end

    subgraph SERVICES["Service Layer (бизнес-логика)"]
        AUTH_S["AuthService<br/>роли: admin / worker / beekeeper"]
        CONSULT_S["ConsultService<br/>KB search → LLM answer"]
        ORDER_S["OrderService<br/>CRUD + status flow + events"]
        ANALYTICS_S["AnalyticsService<br/>10 типов отчётов + LLM classify"]
        DASHBOARD_S["DashboardService<br/>stats + charts + alerts"]
        WORKER_S["WorkerService<br/>state + checklist + queue"]
        DELIVERY_S["DeliveryService<br/>СДЭК / Почта / расчёт"]
        NOTIFY_S["NotificationService<br/>Telegram push"]
    end

    subgraph AGENTS_L["Агенты (тонкие обёртки)"]
        BEEBOT_A["BeebotAgent<br/>→ ConsultService"]
        ANALYST_A["AnalystAgent<br/>→ AnalyticsService"]
        WORKER_A["worker.py<br/>→ WorkerService + UI"]
        LOGIST_A["LogistAgent<br/>→ OrderService"]
        INSPECT_A["InspectorAgent"]
        ADMIN_A["AdminChatAgent"]
    end

    subgraph INFRA_L["Инфраструктура (выход)"]
        CRM_I["CRM v1 / v2<br/>(integram_client)"]
        LLM_I["Groq LLM<br/>(llm_client)"]
        KB_I["FAISS KB<br/>(knowledge_base)"]
        DEL_I["СДЭК / Почта<br/>(delivery/)"]
        MEM_I["SQLite<br/>(memory.py)"]
    end

    TG --> AUTH_S
    TG --> AGENTS_L
    WEB_T --> SERVICES
    REDIS_BUS --> SERVICES

    AGENTS_L --> SERVICES
    SERVICES --> INFRA_L

    style TRANSPORT fill:#e3f2fd
    style SERVICES fill:#e8f5e9,stroke:#22c55e
    style AGENTS_L fill:#fff3e0
    style INFRA_L fill:#f5f5f5
```

### Таблица сервисов

| Сервис | Файл | Зависимости | Ответственность |
|--------|------|-------------|----------------|
| AuthService | `services/auth_service.py` | config (IDs) | Проверка ролей: admin, worker, beekeeper |
| ConsultService | `services/consult_service.py` | KB, LLM, TunnelMonitor | Поиск по KB + генерация ответа, FAQ fallback |
| OrderService | `services/order_service.py` | CRM, NotificationService, EventEmitter | CRUD заказов, status flow, валидация, события |
| AnalyticsService | `services/analytics_service.py` | CRM, Groq | 10 типов отчётов, LLM/keyword classify |
| DashboardService | `services/dashboard_service.py` | CRM | Статистика, графики, алерты для веб-панели |
| WorkerService | `services/worker_service.py` | — | Состояние работника, чеклисты, очередь |
| DeliveryService | `services/delivery_service.py` | Calculator, Tracker | Расчёт доставки, трекинг |
| NotificationService | `services/notification_service.py` | TelegramSender callback | Push в Telegram: пчеловод, клиент, работники |
| StateStore | `services/state_store.py` | Redis (fallback in-memory) | Голос улья, admin mode, worker checklists |
| EventEmitter | `services/event_emitter.py` | EventBus (опц.) | Бизнес-события → SSE + Redis |
| CircuitBreaker | `services/circuit_breaker.py` | — | Защита от каскадных сбоев CRM |

---

## 4. Event-Driven: CQRS + Events

```mermaid
graph LR
    subgraph WRITE["Commands (запись)"]
        CREATE["OrderService<br/>.create_order()"]
        STATUS["OrderService<br/>.update_status()"]
    end

    EMITTER["EventEmitter"]

    subgraph EVENTS["Events"]
        E1["order.created"]
        E2["order.status_changed"]
    end

    subgraph REACT["Subscribers (реакция)"]
        SSE["SSE Bridge<br/>→ push_event()"]
        CACHE["Cache Invalidator<br/>→ invalidate_orders_cache()"]
        REDIS_PUB["Redis Streams<br/>→ stream:events"]
        TG_NOTIFY["NotificationService<br/>→ Telegram push"]
    end

    CREATE -->|"await events.emit()"| EMITTER
    STATUS -->|"await events.emit()"| EMITTER

    EMITTER --> E1 & E2
    E1 & E2 --> SSE & CACHE & REDIS_PUB
    CREATE & STATUS -->|"direct call"| TG_NOTIFY

    style WRITE fill:#e3f2fd
    style EVENTS fill:#fff3e0
    style REACT fill:#e8f5e9,stroke:#22c55e
```

**CQRS (простой):**
- **Queries (чтение):** `get_orders_cache()`, `get_items_cache()` — TTL-кэш, инвалидируется событиями
- **Commands (запись):** `create_order()`, `update_status()` — пишут в CRM, эмитят события, инвалидируют кэш

---

## 5. Оркестратор: маршрутизация интентов

```mermaid
flowchart TD
    MSG["Сообщение от пользователя"] --> FSM{"FSM-состояние?"}

    FSM -->|"OrderFSM"| ORDER_FSM["Шаг диалога заказа<br/>(logist.py)"]
    FSM -->|"InspectFSM"| INSPECT_FSM["Шаг диалога осмотра<br/>(inspector.py)"]
    FSM -->|"Нет"| MODE{"Режим?"}

    MODE -->|"WORKER"| WORKER["Очередь сборки<br/>(worker.py)"]
    MODE -->|"ADMIN /admin"| ADMIN["Ассистент + CRM<br/>(admin_chat.py)"]
    MODE -->|"Обычный"| ORCH["Оркестратор"]

    ORCH --> CLASSIFY{"Классификация intent"}

    CLASSIFY -->|"consult"| BEEBOT["BeebotAgent<br/>→ ConsultService<br/>→ FAISS → LLM"]
    CLASSIFY -->|"order"| START_FSM["Запуск OrderFSM"]
    CLASSIFY -->|"stats"| ANALYST["AnalystAgent<br/>→ AnalyticsService"]
    CLASSIFY -->|"greeting"| GREET["Приветствие"]
    CLASSIFY -->|"edit/track"| MENU["Меню заказа"]
    CLASSIFY -->|"inspect"| START_INSPECT["Запуск InspectFSM"]

    BEEBOT --> RESPONSE["Ответ пользователю"]
    ORDER_FSM & INSPECT_FSM & WORKER & ADMIN & START_FSM & ANALYST & GREET & MENU & START_INSPECT --> RESPONSE

    style ORCH fill:#e3f2fd
    style CLASSIFY fill:#fff3e0
```

---

## 6. Circuit Breaker + Health Check

```mermaid
stateDiagram-v2
    [*] --> CLOSED : Нормальная работа
    CLOSED --> OPEN : 5 ошибок подряд
    OPEN --> HALF_OPEN : timeout (30 сек)
    HALF_OPEN --> CLOSED : Успешный запрос
    HALF_OPEN --> OPEN : Ещё ошибка
```

**`/api/health` возвращает:**
```json
{
  "status": "healthy | degraded | unhealthy",
  "checks": {
    "crm": {"status": "up"},
    "order_service": {"status": "up"},
    "analytics_service": {"status": "up"},
    "bg_tasks": {"crm_snapshot": {"state": "работает", "uptime_sec": 3600}},
    "event_bus": {"status": "up"},
    "crm_circuit_breaker": {"state": "closed", "failures": 0, "threshold": 5}
  }
}
```

---

## 7. StateStore: Redis shared state

```mermaid
graph TB
    subgraph PROCESSES["Процессы"]
        BOT["beebot<br/>(polling)"]
        WEB["beebot-web<br/>(FastAPI)"]
    end

    subgraph STORE["StateStore"]
        REDIS_STORE["Redis :6379"]
        FALLBACK["In-memory<br/>(fallback)"]
    end

    subgraph KEYS["Redis Keys"]
        K1["beebot:user_styles<br/>(Hash)"]
        K2["beebot:admin_mode<br/>(Set)"]
        K3["beebot:admin_view<br/>(Hash)"]
        K4["beebot:worker:checklist:*<br/>(Set per order)"]
    end

    BOT --> STORE
    WEB --> STORE
    STORE --> KEYS

    style STORE fill:#e8f5e9,stroke:#22c55e
    style KEYS fill:#fff8e1
```

**Best practice:** Состояние переживает рестарт. Worker checklists не теряются.

---

## 8. BackgroundTaskManager: фоновые задачи

```mermaid
graph LR
    BG["BackgroundTaskManager<br/>(bg_tasks.py)"]

    BG -->|"crm_snapshot"| SNAP["CrmSnapshot<br/>каждые 5 мин"]
    BG -->|"order_tracker"| TRACK["OrderTracker<br/>каждые 2 часа"]
    BG -->|"uds_poller"| UDS["UDSPoller<br/>каждые 5 мин"]
    BG -->|"tunnel_monitor"| TUN["TunnelMonitor<br/>каждые 60 сек"]
    BG -->|"backup"| BACK["BackupManager<br/>ежедневно"]

    BG -.->|"alert_fn"| TG["Telegram алерт<br/>пчеловоду"]

    style BG fill:#e3f2fd,stroke:#1976d2
```

**Возможности:**
- Авто-рестарт при падении (экспоненциальная пауза, макс 60 сек)
- Мониторинг: `bg.status()` → состояние, uptime, число рестартов
- Graceful shutdown: `bg.stop_all()` при остановке

---

## 9. Жизненный цикл заказа

```mermaid
stateDiagram-v2
    [*] --> Новый : Telegram / UDS / Веб

    Новый --> Подтверждён : Пчеловод проверяет
    Новый --> Отменён : Отказ

    Подтверждён --> В_сборке : Работник берёт
    Подтверждён --> Отменён : Нет товара

    В_сборке --> Отправлен : Трек-номер
    В_сборке --> Отменён : Проблема

    Отправлен --> Доставлен : Трекер подтвердил
```

### Источники заказов

| Источник | Как попадает | Уведомления |
|----------|-------------|-------------|
| Telegram FSM | LogistAgent → OrderService → CRM → EventEmitter | Пчеловод + работники + SSE |
| UDS-магазин | UDSPoller → CRM | Пчеловод + работники |
| Веб-панель | orders.py → OrderService → CRM → EventEmitter | Пчеловод + SSE |

---

## 10. CRM: две системы

```mermaid
graph TB
    subgraph APP["BEEBOT"]
        FF{{"INTEGRAM_V2<br/>feature flag"}}
        V1_CL["IntegramClient<br/>(v1)"]
        V2_CL["IntegramV2Client<br/>(v2)"]
        PROXY["_SingletonCrmProxy<br/>close() = no-op"]
    end

    subgraph V1["ai2o.ru (АРХИВ)"]
        V1_DB[("bibot<br/>1924 клиента<br/>1915 заказов<br/>76 товаров")]
    end

    subgraph V2["ai2o.online (ОСНОВНАЯ)"]
        V2_DB[("alekseymavai<br/>85 товаров<br/>4 справочника<br/>чистые данные")]
    end

    FF -->|"true"| V2_CL --> V2_DB
    FF -->|"false"| V1_CL --> V1_DB
    V1_CL & V2_CL --> PROXY

    style V1 fill:#fee2e2
    style V2 fill:#bbf7d0
    style FF fill:#fef3c7
    style PROXY fill:#e3f2fd
```

**Singleton CRM:** создаётся один раз в `startup.py`, оборачивается в `_SingletonCrmProxy` (close() — no-op), раздаётся 37 роутерам через `_get_crm()`.

---

## 11. Инфраструктура: единый Docker-образ

```mermaid
graph TB
    subgraph VPS["VPS 185.233.200.13"]
        subgraph DOCKER["Docker Compose"]
            BOT_C["beebot<br/>python -m src.bot<br/>~762 MiB"]
            WEB_C["beebot-web<br/>uvicorn :8088<br/>+ Vue dist"]
            REDIS_C["Redis<br/>:6379<br/>32 MiB"]
        end
        NOTE_IMG["Один образ:<br/>Python + FAISS +<br/>Node build → Vue dist"]
    end

    subgraph HIVE["Hive (локальная)"]
        GROQ_P["groq-proxy :8990"]
        SOCKS["SOCKS5 :9150"]
        DEVBOT_C["DEVBOT :8091"]
    end

    subgraph CLOUD["Облачные сервисы"]
        TG_API["Telegram API"]
        GROQ_API["Groq API"]
        CRM_V2_C["ai2o.online"]
        UDS_C["UDS Partner API"]
        CDEK["СДЭК API"]
        POCHTA["Почта России"]
    end

    BOT_C -->|"SSH tunnel"| GROQ_P --> GROQ_API
    BOT_C -->|"SOCKS5"| SOCKS --> TG_API
    BOT_C & WEB_C --> REDIS_C
    BOT_C & WEB_C --> CRM_V2_C
    BOT_C -->|"polling 5 мин"| UDS_C
    WEB_C --> CDEK & POCHTA

    NOTE_IMG -.->|"единый<br/>Dockerfile"| BOT_C & WEB_C

    style VPS fill:#e3f2fd
    style HIVE fill:#f3e5f5
    style NOTE_IMG fill:#fff8e1,stroke:#f9a825
```

### Docker-контейнеры

| Контейнер | Образ | Команда | RAM | Порт |
|-----------|-------|---------|-----|------|
| redis | redis:7-alpine | — | ~20 MiB | 6379 |
| beebot | **Единый** (Python + FAISS + Vue) | `python -m src.bot` | ~762 MiB | — |
| beebot-web | **Единый** (тот же образ) | `uvicorn src.web.server:app` | ~200 MiB | 8088 |

**Было:** два Dockerfile (Dockerfile + Dockerfile.web). **Стало:** один Dockerfile с multi-stage (Node → Vue build + Python deps).

---

## 12. Файловая структура: пять слоёв

```mermaid
graph TB
    subgraph TRANSPORT["Транспорт (вход)"]
        TG["Telegram<br/>bot.py + 5 роутеров"]
        WEB_T["FastAPI<br/>api.py + 9 роутеров"]
        REDIS_T["Redis Streams<br/>bus_handlers.py"]
    end

    subgraph INIT["Инициализация"]
        STARTUP_F["startup.py<br/>create_services()"]
    end

    subgraph SVC["Service Layer (10 сервисов)"]
        AUTH_F["auth_service.py"]
        CONSULT_F["consult_service.py"]
        ORDER_F["order_service.py"]
        ANALYTICS_F["analytics_service.py"]
        DASHBOARD_F["dashboard_service.py"]
        WORKER_F["worker_service.py"]
        DELIVERY_F["delivery_service.py"]
        NOTIFY_F["notification_service.py"]
        STATE_F["state_store.py"]
        EVENTS_F["event_emitter.py"]
        CB_F["circuit_breaker.py"]
    end

    subgraph AGENTS_F["Агенты (обёртки)"]
        BEEBOT_F["beebot.py → ConsultService"]
        ANALYST_F["analyst.py → AnalyticsService"]
        WORKER_AF["worker.py → WorkerService + UI"]
        LOGIST_F["logist.py → OrderService"]
        INSPECT_F["inspector.py"]
        ADMIN_F["admin_chat.py"]
    end

    subgraph INFRA_F["Инфраструктура"]
        CRM_F["integram_client.py<br/>crm_factory.py"]
        LLM_F["llm_client.py<br/>tunnel_monitor.py"]
        KB_F["knowledge_base.py<br/>FAISS + стилометрия"]
        DEL_F["delivery/<br/>cdek + pochta + calculator"]
        MEM_F["memory.py<br/>SQLite"]
    end

    TRANSPORT --> INIT --> SVC
    TRANSPORT --> AGENTS_F
    AGENTS_F --> SVC
    SVC --> INFRA_F

    style TRANSPORT fill:#e3f2fd
    style INIT fill:#fff8e1,stroke:#f9a825
    style SVC fill:#e8f5e9,stroke:#22c55e
    style AGENTS_F fill:#fff3e0
    style INFRA_F fill:#f5f5f5
```

---

## 13. Поток консультации: пользователь → ответ

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Bot as Telegram-бот
    participant Orch as Оркестратор
    participant Agent as BeebotAgent
    participant Svc as ConsultService
    participant KB as FAISS (276 чанков)
    participant LLM as Groq (llama-3.3-70b)

    User->>Bot: "Чем полезна перга?"
    Bot->>Orch: route(query, user_id)
    Orch->>Orch: classify → "consult"
    Orch->>Agent: answer(query, history, style)
    Agent->>Svc: answer(query, ...)
    Svc->>KB: search(query, top_k=5)
    KB-->>Svc: [chunk1, chunk2, chunk3]
    Svc->>LLM: system_prompt + chunks + query
    LLM-->>Svc: "Перга — это пыльца..."
    Svc-->>Agent: (response, chunks)
    Agent-->>Orch: (response, chunks)
    Orch-->>Bot: response
    Bot-->>User: "Перга — это пыльца..."
```

---

## 14. Поток заказа: FSM → OrderService → Events

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Bot as Telegram-бот
    participant FSM as OrderFSM
    participant Logist as LogistAgent
    participant OS as OrderService
    participant CRM as Integram CRM
    participant EE as EventEmitter
    participant SSE as SSE (веб-панель)

    User->>Bot: /order
    Bot->>FSM: start
    FSM->>Logist: start_order()
    Logist->>CRM: get_products()
    CRM-->>Logist: [85 товаров]
    Logist-->>FSM: каталог + клавиатура

    loop 7 шагов
        FSM-->>User: Вопрос (товары/ФИО/телефон/адрес/доставка)
        User->>FSM: Ответ
    end

    FSM->>Logist: create_order(client, items, delivery)
    Logist->>OS: create_order()
    OS->>CRM: create_order()
    OS->>OS: notify (пчеловод + работники)
    OS->>EE: emit("order.created", {...})
    EE->>SSE: push_event() → веб-панель обновляется
    EE->>EE: invalidate_orders_cache()
    Bot-->>User: "Заказ #TG-20260402 создан!"
```

---

## 15. UDS-синхронизация: магазин → CRM

```mermaid
sequenceDiagram
    participant UDS as UDS Partner API
    participant Poller as UDSPoller<br/>(каждые 5 мин)
    participant Dedup as TransactionDeduplicator
    participant CRM as Integram CRM
    participant Bot as Telegram-бот
    participant Admin as Пчеловод

    Note over Poller: Старт бота
    Poller->>CRM: get_orders() — загрузить UDS-* заказы
    CRM-->>Dedup: {UDS-001, UDS-002, ...}

    Note over Poller: Catch-up с 01.01.2024
    Poller->>UDS: get_transactions_since(2024-01-01)
    UDS-->>Poller: [tx1, tx2, ..., txN]
    loop Каждая транзакция
        Poller->>Dedup: is_new(tx)?
        alt Новая
            Poller->>CRM: get_or_create_client(phone)
            Poller->>CRM: get_product_by_sku(sku)
            Poller->>CRM: create_order(source="UDS")
            Dedup->>Dedup: mark_seen(tx.id)
        end
    end

    Note over Poller: Обычный polling
    loop Каждые 5 минут
        Poller->>UDS: get_transactions(limit=50)
        UDS-->>Poller: [последние транзакции]
        Poller->>Dedup: is_new(tx)?
        alt Новая
            Poller->>CRM: sync_uds_transaction()
            Poller->>Bot: уведомление
            Bot->>Admin: 🛒 Новый заказ из UDS
        end
    end
```

---

## 16. Голос Улья: 5 стилей

| Стиль | Описание | Когда использовать |
|-------|---------|-------------------|
| Наставник | Тёплый, отеческий тон | По умолчанию |
| Практик | Конкретные советы, цифры | Опытные пчеловоды |
| Селекционер | Научный подход, исследования | Вопросы о генетике, породах |
| Зимовщик | Спокойный, вдумчивый | Зимний период, подготовка |
| Эколог | Природа, экосистема | Вопросы о среде обитания |

---

*Связанные документы: [analysis.md](../analysis.md) | [plan.md](../plan.md) | [README.md](../README.md)*
