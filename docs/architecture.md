# BEEBOT — Архитектурные диаграммы

> **Версия:** 3 апреля 2026 (обновлено: Service Layer refactoring)

---

## 1. Общая архитектура

```mermaid
graph TB
    subgraph USERS["Пользователи"]
        U1["Подписчики<br/>(Telegram)"]
        U2["Пчеловод<br/>(Admin)"]
        U3["Работники<br/>(Worker)"]
        U4["Веб-панель<br/>(Браузер)"]
    end

    subgraph BOT["Telegram-бот (Docker)"]
        HANDLERS["Роутеры aiogram<br/>admin / user / fsm / inspect / worker"]
        ORCH["Оркестратор<br/>(LangGraph)"]
        AGENTS["6 агентов"]
    end

    subgraph SVC_LAYER["Service Layer"]
        AUTH["AuthService"]
        ORDER_SVC["OrderService"]
        CONSULT["ConsultService"]
        ANALYTICS["AnalyticsService"]
        WORKER_SVC["WorkerService"]
        DELIVERY_SVC["DeliveryService"]
        NOTIFY["NotificationService"]
    end

    subgraph WEB["Веб-панель (Docker)"]
        API["FastAPI :8088"]
        VUE["Vue 3 PWA<br/>14 страниц"]
        BUS["BusHandlers<br/>(Redis Streams)"]
        BG["BackgroundTaskManager"]
    end

    subgraph INFRA["Инфраструктура"]
        CRM_V2[("ai2o.online<br/>CRM v2")]
        CRM_V1[("ai2o.ru<br/>CRM v1 архив")]
        KB["FAISS<br/>276 чанков"]
        LLM["Groq API<br/>llama-3.3-70b"]
        MEM["SQLite<br/>память"]
    end

    subgraph EXTERNAL["Внешние системы"]
        UDS_API["UDS App<br/>(магазин)"]
        CDEK_A["СДЭК API"]
        POCHTA_A["Почта России"]
    end

    U1 & U2 & U3 --> BOT
    U4 --> VUE --> API

    HANDLERS --> ORCH --> AGENTS
    AGENTS --> SVC_LAYER
    API --> SVC_LAYER
    BUS --> SVC_LAYER
    SVC_LAYER --> KB & LLM & MEM & CRM_V2
    SVC_LAYER -.->|"read-only"| CRM_V1

    UDS_API -->|"polling 5 мин"| BG
    BG -->|"авто-трекинг 2ч"| CDEK_A & POCHTA_A

    style SVC_LAYER fill:#e8f5e9,stroke:#22c55e
    style CRM_V2 fill:#bbf7d0,stroke:#22c55e
    style CRM_V1 fill:#fee2e2,stroke:#ef4444
    style EXTERNAL fill:#f3e5f5
```

---

## 2. Service Layer: архитектура слоёв

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
        ORDER_S["OrderService<br/>CRUD + status flow + notify"]
        ANALYTICS_S["AnalyticsService<br/>10 типов отчётов + LLM classify"]
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
| OrderService | `services/order_service.py` | CRM, NotificationService | CRUD заказов, status flow, валидация |
| AnalyticsService | `services/analytics_service.py` | CRM, Groq | 10 типов отчётов, LLM/keyword classify |
| WorkerService | `services/worker_service.py` | — (in-memory) | Состояние работника, чеклисты, очередь |
| DeliveryService | `services/delivery_service.py` | Calculator, Tracker | Расчёт доставки, трекинг |
| NotificationService | `services/notification_service.py` | TelegramSender callback | Push в Telegram: пчеловод, клиент, работники |

---

## 3. Оркестратор: маршрутизация интентов

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

## 4. Агенты: зависимости и делегирование

```mermaid
graph LR
    subgraph AGENTS["Агенты (UI + делегирование)"]
        BEEBOT["Консультант<br/>(beebot.py)"]
        LOGIST["Логист<br/>(logist.py)"]
        ANALYST["Аналитик<br/>(analyst.py)"]
        INSPECTOR["Инспектор<br/>(inspector.py)"]
        ADMIN_CHAT["Ассистент<br/>(admin_chat.py)"]
        WORKER_A["Работник<br/>(worker.py)"]
    end

    subgraph SERVICES["Сервисы"]
        CS["ConsultService"]
        AS["AnalyticsService"]
        OS["OrderService"]
        WS["WorkerService"]
    end

    KB["FAISS KB"]
    LLM["Groq LLM"]
    CRM["CRM"]

    BEEBOT -->|"делегирует"| CS
    ANALYST -->|"делегирует"| AS
    LOGIST -->|"делегирует"| OS
    WORKER_A -->|"делегирует"| WS

    CS --> KB & LLM
    AS --> CRM & LLM
    OS --> CRM
    WS --> CRM
    INSPECTOR --> KB & LLM
    ADMIN_CHAT --> CRM & LLM

    style AGENTS fill:#fff3e0
    style SERVICES fill:#e8f5e9,stroke:#22c55e
```

### Сравнительная таблица агентов

| Агент | Сервис | KB | CRM | LLM | Вход | Выход |
|---|---|---|---|---|---|---|
| Консультант | ConsultService | Чтение | — | Groq | consult | Текст + источники |
| Логист | OrderService | — | Запись | Groq | order (FSM) | Заказ в CRM |
| Аналитик | AnalyticsService | — | Чтение | Groq | stats | Отчёт (текст) |
| Инспектор | — | Чтение | — | Groq | /inspect (FSM) | Рекомендация |
| Ассистент | — | — | CrmSnapshot | Groq | /admin | Диалог |
| Работник | WorkerService | — | Чтение+Запись | — | /start (worker) | Кнопки |

---

## 5. BackgroundTaskManager: фоновые задачи

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
- Graceful shutdown: `bg.stop_all()` при остановке бота

---

## 6. Жизненный цикл заказа

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
| Telegram FSM | LogistAgent → OrderService → CRM | Пчеловод + работники |
| UDS-магазин | UDSPoller → CRM | Пчеловод + работники |
| Веб-панель | orders.py → CRM | Только пчеловод |

---

## 7. CRM: две системы

```mermaid
graph TB
    subgraph APP["BEEBOT"]
        FF{{"INTEGRAM_V2<br/>feature flag"}}
        V1_CL["IntegramClient<br/>(v1)"]
        V2_CL["IntegramV2Client<br/>(v2)"]
    end

    subgraph V1["ai2o.ru (АРХИВ)"]
        V1_DB[("bibot<br/>1924 клиента<br/>1915 заказов<br/>76 товаров")]
    end

    subgraph V2["ai2o.online (ОСНОВНАЯ)"]
        V2_DB[("alekseymavai<br/>85 товаров<br/>4 справочника<br/>чистые данные")]
    end

    FF -->|"true"| V2_CL --> V2_DB
    FF -->|"false"| V1_CL --> V1_DB

    style V1 fill:#fee2e2
    style V2 fill:#bbf7d0
    style FF fill:#fef3c7
```

### Схема таблиц CRM v2

```mermaid
erDiagram
    CATEGORIES["Категории (151)"] ||--o{ PRODUCTS["Товары (581)"] : "группирует"
    SOURCES["Источники (15)"] ||--o{ CLIENTS["Клиенты (52)"] : "канал"
    SOURCES ||--o{ ORDERS["Заказы (60)"] : "канал"
    STATUSES["Статусы (152)"] ||--o{ ORDERS : "текущий"
    DELIVERY["Доставка (150)"] ||--o{ ORDERS : "способ"
    CLIENTS ||--o{ ORDERS : "размещает"
    ORDERS ||--o{ ORDER_ITEMS["Позиции (78)"] : "содержит"
    PRODUCTS ||--o{ ORDER_ITEMS : "товар"

    PRODUCTS {
        int id PK
        string name
        float price
        int stock
        ref category
    }

    CLIENTS {
        int id PK
        string full_name
        string phone
        int telegram_id
        string city
    }

    ORDERS {
        int id PK
        datetime date
        ref client
        ref status
        ref delivery
        float total
        string tracking
    }

    ORDER_ITEMS {
        int id PK
        ref order
        ref product
        int quantity
        float price
    }
```

---

## 8. Инфраструктура: туннели и деплой

```mermaid
graph TB
    subgraph VPS["VPS 185.233.200.13"]
        BOT_C["beebot<br/>~762 MiB"]
        WEB_C["beebot-web<br/>:8088"]
        REDIS_C["Redis<br/>:6379"]
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
    BOT_C --> REDIS_C --> WEB_C
    BOT_C & WEB_C --> CRM_V2_C
    BOT_C -->|"polling 5 мин"| UDS_C
    WEB_C --> CDEK & POCHTA

    style VPS fill:#e3f2fd
    style HIVE fill:#f3e5f5
```

### Docker-контейнеры

| Контейнер | Образ | RAM | Порт |
|-----------|-------|-----|------|
| redis | redis:7-alpine | ~20 MiB | 6379 |
| beebot | Python 3.12 + FAISS + Groq | ~762 MiB | — |
| beebot-web | Python 3.12 + Vue dist | ~50 MiB | 8088 |

---

## 9. Файловая структура: четыре слоя

```mermaid
graph TB
    subgraph TRANSPORT["Транспорт (вход)"]
        TG["Telegram<br/>bot.py + 5 роутеров"]
        WEB_T["FastAPI<br/>api.py + 9 роутеров"]
        REDIS_T["Redis Streams<br/>bus_handlers.py"]
    end

    subgraph SVC["Service Layer"]
        AUTH_F["auth_service.py"]
        CONSULT_F["consult_service.py"]
        ORDER_F["order_service.py"]
        ANALYTICS_F["analytics_service.py"]
        WORKER_F["worker_service.py"]
        DELIVERY_F["delivery_service.py"]
        NOTIFY_F["notification_service.py"]
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

    TRANSPORT --> SVC
    TRANSPORT --> AGENTS_F
    AGENTS_F --> SVC
    SVC --> INFRA_F

    style TRANSPORT fill:#e3f2fd
    style SVC fill:#e8f5e9,stroke:#22c55e
    style AGENTS_F fill:#fff3e0
    style INFRA_F fill:#f5f5f5
```

---

## 10. Поток консультации: пользователь → ответ

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

## 11. Поток заказа: FSM 7 шагов

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Bot as Telegram-бот
    participant FSM as OrderFSM
    participant Logist as LogistAgent
    participant OS as OrderService
    participant CRM as Integram CRM

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
    Bot-->>User: "Заказ #TG-20260402 создан!"
```

---

## 12. UDS-синхронизация: магазин → CRM

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

### Компоненты UDS-интеграции

| Компонент | Файл | Назначение |
|-----------|------|-----------|
| UDSClient | src/integrations/uds.py | REST-клиент UDS Partner API v2 (Basic Auth, retry 3×) |
| UDSPoller | src/integrations/uds.py | Фоновый polling + catch-up + дедупликация |
| TransactionDeduplicator | src/integrations/uds.py | Хранит обработанные ID, загружает из CRM при старте |
| sync_uds_transaction() | src/integrations/uds.py | Транзакция → клиент → товары по SKU → заказ → уведомление |
| sync_uds_catalog() | src/integrations/uds.py | Сопоставление каталога UDS ↔ Integram по артикулу |

---

## 13. Голос Улья: 5 стилей

| Стиль | Описание | Когда использовать |
|-------|---------|-------------------|
| Наставник | Тёплый, отеческий тон | По умолчанию |
| Практик | Конкретные советы, цифры | Опытные пчеловоды |
| Селекционер | Научный подход, исследования | Вопросы о генетике, породах |
| Зимовщик | Спокойный, вдумчивый | Зимний период, подготовка |
| Эколог | Природа, экосистема | Вопросы о среде обитания |

---

*Связанные документы: [analysis.md](../analysis.md) | [plan.md](../plan.md) | [README.md](../README.md)*
