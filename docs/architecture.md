# BEEBOT — Архитектурные диаграммы

> Версия: 18 марта 2026

---

## 1. Общая архитектура системы

```mermaid
graph TB
    subgraph Пользователи
        TG[📱 Telegram<br/>подписчики]
        WEB[💻 Веб-панель<br/>пчеловод / менеджер]
    end

    subgraph VPS["VPS (Docker)"]
        BOT[Telegram-бот<br/>aiogram 3]
        ORCH[Оркестратор<br/>LangGraph]
        BEEBOT_A[🐝 Консультант<br/>FAISS → LLM]
        LOGIST[📦 Логист<br/>FSM 7 шагов]
        ANALYST[📊 Аналитик<br/>статистика]
        API[FastAPI<br/>REST API + JWT]
        FAISS[FAISS<br/>410 чанков]
        TRACKER[Авто-трекинг<br/>каждые 2 часа]
        SSE[SSE-сервер<br/>real-time events]
    end

    subgraph Внешние["Внешние сервисы"]
        GROQ[Groq API<br/>llama-3.3-70b]
        CRM[Integram CRM<br/>ai2o.ru/bibot]
        CDEK[СДЭК API v2<br/>OAuth2]
        POCHTA[Почта России<br/>tariff.pochta.ru]
        UDS[UDS API<br/>система лояльности]
    end

    subgraph HIVE["Hive (локальная)"]
        PROXY[groq-proxy<br/>порт 8990]
        TUNNEL[SSH-туннель<br/>auto-restart]
    end

    TG --> BOT
    WEB --> API
    WEB -.->|SSE| SSE
    BOT --> ORCH
    ORCH --> BEEBOT_A
    ORCH --> LOGIST
    ORCH --> ANALYST
    BEEBOT_A --> FAISS
    BEEBOT_A --> TUNNEL
    LOGIST --> CRM
    LOGIST --> CDEK
    LOGIST --> POCHTA
    ANALYST --> CRM
    API --> CRM
    TRACKER --> CRM
    TRACKER --> CDEK
    TRACKER --> POCHTA
    TUNNEL --> PROXY --> GROQ
    UDS -.->|поллер| CRM
```

---

## 2. Поток обработки сообщения

```mermaid
sequenceDiagram
    participant U as 👤 Пользователь
    participant B as 🤖 Telegram-бот
    participant O as 🧭 Оркестратор
    participant KB as 📚 FAISS
    participant LLM as 🧠 Groq LLM
    participant CRM as 🗄️ Integram

    U->>B: Текстовое сообщение
    B->>O: route(message, user_id)
    O->>O: Загрузить историю (до 5 пар)
    O->>LLM: Определить интент (~100 токенов)
    LLM-->>O: "consult" | "order" | "delivery" | "status" | "stats" | "chitchat"

    alt consult
        O->>KB: search(query, top_k=5)
        KB-->>O: 5 чанков (семантика 70% + стилометрия 30%)
        O->>LLM: generate(context + history + system_prompt)
        LLM-->>O: Ответ в стиле автора
        O->>O: Сохранить в историю
        O-->>B: Текст + кнопки [📄 PDF] [🛒 Каталог]
    else order
        O->>B: Запуск FSM логиста
        Note over B: 7 шагов оформления →
        B->>CRM: create_order + позиции
        B-->>U: Заказ создан ✅
    else stats (только ADMIN)
        O->>CRM: Аналитические запросы
        O-->>B: Таблицы + графики
    else chitchat
        O->>LLM: Дружелюбный ответ
        O-->>B: Текст
    end

    B-->>U: Ответ
```

---

## 3. Гибридный поиск в базе знаний

```mermaid
graph LR
    Q[🔍 Запрос<br/>пользователя] --> EMB[Эмбеддинг<br/>MiniLM-L12-v2]

    EMB --> SEM[Семантический поиск<br/>FAISS cosine similarity<br/>Вес: 70%]
    EMB --> STY[Стилометрия<br/>длина предложений,<br/>средняя длина слов,<br/>знаки препинания<br/>Вес: 30%]

    SEM --> MERGE[Объединение скоров<br/>combined = 0.7×sem + 0.3×sty]
    STY --> MERGE

    Q --> KW[Keyword-буст<br/>прямое попадание<br/>по ключевым словам]
    KW --> MERGE

    MERGE --> TOP5[Топ-5 чанков<br/>с метаданными]
    TOP5 --> LLM[LLM генерация<br/>в стиле Александра]
```

**Источники данных (410 чанков):**

| Тип | Кол-во файлов | Описание |
|-----|---------------|----------|
| PDF-инструкции | 19 | Перга, прополис, ПЖВМ, гомогенат, маточное молочко и др. |
| Тексты | 21 | Очищенные выдержки из PDF |
| YouTube субтитры | 26 | Расшифровки видео с канала @a.dmitrov |

**Алгоритм keyword-буста:**
```
Запрос: "как принимать пергу"
  → ключевое слово "перга" найдено
  → чанки из "Перга.txt" получают +0.5 к скору
  → гарантированное попадание нужного документа в топ-5
```

---

## 4. FSM оформления заказа (Логист)

```mermaid
stateDiagram-v2
    [*] --> ВыборТовара: Интент "order"
    ВыборТовара --> ФИО: Товар выбран (из каталога CRM)
    ФИО --> Телефон: ФИО введено
    Телефон --> Адрес: Телефон валиден (+7XXXXXXXXXX)
    Адрес --> Доставка: Адрес введён
    Доставка --> Подтверждение: Способ выбран + стоимость
    Подтверждение --> СозданиеЗаказа: [✅ Подтвердить]
    Подтверждение --> [*]: [❌ Отменить]
    СозданиеЗаказа --> СохранениеВCRM
    СохранениеВCRM --> УведомлениеАдмину
    УведомлениеАдмину --> [*]

    note right of ВыборТовара
        Каталог из CRM (76 товаров)
        Только in_stock=True
        Inline-кнопки по категориям
    end note

    note right of ФИО
        Авто-подстановка по Telegram ID
        Имя, телефон, адрес
    end note

    note right of Телефон
        phone_utils.py: validate_phone()
        +7/8/9xx → +7XXXXXXXXXX
        "Да" = использовать сохранённый
    end note

    note right of Доставка
        СДЭК API v2 (OAuth2)
        Почта России (tariff.pochta.ru)
        Самовывоз: 0₽
    end note

    note left of Подтверждение
        Таймаут: 15 мин
        asyncio.Lock
    end note

    note right of СохранениеВCRM
        create_order() +
        add_order_items() +
        recalculate_totals()
    end note
```

---

## 5. Жизненный цикл заказа

```mermaid
stateDiagram-v2
    [*] --> Новый: Заказ создан (бот / веб)
    Новый --> Подтверждён: Пчеловод подтвердил
    Подтверждён --> ВСборке: Взят в сборку
    ВСборке --> Отправлен: Трек-номер введён
    Отправлен --> Доставлен: Авто-трекинг или вручную
    Новый --> Отменён: На любом этапе
    Подтверждён --> Отменён
    ВСборке --> Отменён

    note right of Новый
        Источники:
        • Telegram-бот (FSM логиста)
        • UDS-поллер (sync)
        • Веб-панель (TODO)
    end note

    note right of Подтверждён
        PWA Сборка:
        видит заказ в чеклисте
    end note

    note right of Отправлен
        Клиент получает трек-номер
        (Telegram уведомление)
        Авто-трекинг каждые 2 часа
    end note

    note right of Доставлен
        Авто-обновление из СДЭК/Почта
        Уведомление клиенту
        SSE-событие в веб-панель
    end note
```

---

## 6. Каналы уведомлений

```mermaid
graph TB
    subgraph Триггеры
        T1[Новый заказ<br/>бот / UDS]
        T2[Смена статуса<br/>веб-панель]
        T3[Трек-номер<br/>веб-панель]
        T4[Доставлен<br/>авто-трекинг]
    end

    subgraph Каналы
        TG_ADMIN[📱 Telegram<br/>пчеловоду]
        TG_CLIENT[📱 Telegram<br/>клиенту]
        SSE_WEB[🖥️ SSE<br/>веб-панель]
    end

    T1 -->|notify_admin()| TG_ADMIN
    T2 -->|notify_client_status_change()| TG_CLIENT
    T2 -->|push_event()| SSE_WEB
    T3 -->|notify_client_tracking()| TG_CLIENT
    T3 -->|push_event()| SSE_WEB
    T4 -->|notify_fn()| TG_CLIENT

    style T1 fill:#e1f5fe
    style T4 fill:#e8f5e9
```

**Известное расхождение:** Смена статуса через бота НЕ отправляет SSE. Смена через веб-панель НЕ уведомляет пчеловода в Telegram.

---

## 7. Инфраструктура и деплой

```mermaid
graph TB
    subgraph VPS["VPS 185.233.200.13"]
        subgraph Docker
            C1[beebot<br/>Telegram-бот + FAISS<br/>network_mode: host]
            C2[beebot-web<br/>FastAPI + Vue PWA<br/>порт 8088→8080]
        end
        VOL1[(data/processed<br/>FAISS индекс)]
        VOL2[(data/subtitles)]
        VOL3[(.env<br/>секреты)]
    end

    subgraph Hive["Hive (локальная машина)"]
        GP[groq-proxy.service<br/>порт 8990]
        GT[groq-tunnel.service<br/>SSH auto-restart]
    end

    subgraph CI["GitHub Actions"]
        LINT[ruff lint]
        TEST[pytest]
        DEPLOY[SSH deploy<br/>git pull + docker build]
    end

    subgraph External["Внешние"]
        GROQ[api.groq.com]
        TGAPI[api.telegram.org]
        ICRM[ai2o.ru<br/>Integram CRM]
        GH[GitHub<br/>alekseymavai/BEEBOT]
    end

    C1 --> TGAPI
    C1 --> ICRM
    C1 -.->|SSH-туннель:8990| GT
    GT -.->|localhost:8990| GP
    GP --> GROQ
    C2 --> ICRM
    C1 --- VOL1
    C1 --- VOL2
    C1 --- VOL3
    GH -->|push to main| CI
    CI -->|SSH| DEPLOY
    DEPLOY -->|git pull + build| VPS
```

### CI/CD пайплайн

```mermaid
graph LR
    PR[Pull Request] --> LINT[ruff check]
    LINT --> TEST[pytest -x]
    TEST --> MERGE[Merge to main]
    MERGE --> DEPLOY[Deploy job]
    DEPLOY --> SSH[SSH to VPS]
    SSH --> PULL[git pull]
    PULL --> BUILD[docker compose up -d --build]
    BUILD --> DONE[✅ Production updated]
```

---

## 8. Веб-панель (PWA)

```mermaid
graph LR
    subgraph Frontend["Vue 3 + PrimeVue"]
        DASH[📊 Дашборд<br/>6 карточек + 4 графика]
        ORD[📋 Заказы<br/>список + детали + создание]
        CLI[👥 Клиенты<br/>список + карточка]
        PROD[📦 Товары<br/>CRUD + остатки]
        PACK[✅ Сборка<br/>PWA offline]
        STOCK[🏭 Склад<br/>PWA offline]
        JOUR[📅 Журнал<br/>по месяцам]
    end

    subgraph PWA["PWA / Offline"]
        SW[Service Worker<br/>кэш статики]
        IDB[IndexedDB<br/>кэш API + sync queue]
    end

    subgraph Backend["FastAPI API"]
        AUTH[POST /api/auth/token<br/>JWT]
        APID[GET /api/dashboard]
        APIO[GET /api/orders<br/>+ пагинация + поиск]
        APIC[GET /api/clients<br/>+ пагинация]
        APIP[GET /api/products<br/>+ пагинация]
        APIE[GET /api/export/*<br/>CSV]
        APISSE[GET /api/events<br/>SSE]
        APIREF[GET /api/reference<br/>справочники]
    end

    DASH --> APID
    ORD --> APIO
    CLI --> APIC
    PROD --> APIP
    PACK --> APIO
    STOCK --> APIP
    JOUR --> APIO
    PACK -.-> IDB
    STOCK -.-> IDB
    Frontend --> AUTH
```

---

## 9. CRM-архитектура (Integram)

```mermaid
graph TB
    subgraph Код["Python-слой"]
        API_LOW[IntegramAPI<br/>integram_api.py<br/>HTTP: get/post/set_requisites]
        API_HIGH[IntegramClient<br/>integram_client.py<br/>get_orders, create_order, ...]
        SCHEMA[crm_schema.py<br/>TYPE_IDS, REQ_IDS]
        CONST[crm_constants.py<br/>STATUS_IDS, SOURCE_IDS]
    end

    subgraph CRM["Integram CRM (ai2o.ru/bibot)"]
        T_ORDERS[📋 Заказы<br/>type_id=212]
        T_CLIENTS[👥 Клиенты<br/>type_id=213]
        T_PRODUCTS[📦 Товары<br/>type_id=214]
        T_ITEMS[📝 Позиции<br/>type_id=215]
        L_STATUS[Статусы (6)]
        L_SOURCE[Источники (6)]
        L_DELIVERY[Доставка (3)]
        L_CATEGORY[Категории (8)]
    end

    API_HIGH --> API_LOW
    API_LOW --> CRM
    API_HIGH --> SCHEMA
    API_HIGH --> CONST
```

### Таблицы CRM

| Таблица | ID типа | Записей | Ключевые поля |
|---------|---------|---------|---------------|
| Товары | 214 | 76 | Название, Цена, Категория, В наличии, SKU UDS |
| Клиенты | 213 | 285+ | ФИО, Телефон, Telegram ID, Город, Источник |
| Заказы | 212 | 326+ | Номер, Клиент, Статус, Доставка, Сумма, Трек |
| Позиции заказа | 215 | ~800 | Заказ, Товар, Количество, Цена, Сумма |

### Справочники

| Справочник | Значения |
|-----------|----------|
| Статусы | Новый, Подтверждён, В сборке, Отправлен, Доставлен, Отменён |
| Источники | Telegram, UDS, Сайт, Звонок, WhatsApp, Другое |
| Доставка | СДЭК, Почта России, Самовывоз |
| Категории | Мёд, Перга, Прополис, ПЖВМ, Маточное молочко, Воск, Настойки, Программы |

---

## 10. Сравнение модулей

| Модуль | Строк | Тестов | Зависимости | Состояние |
|--------|-------|--------|-------------|-----------|
| `bot.py` | 980 | ~10 | aiogram, LangGraph, CRM | ✅ Production |
| `orchestrator.py` | 371 | ~30 | LangGraph, Groq, history | ✅ Production |
| `agents/beebot.py` | 86 | ~35 | FAISS, Groq | ✅ Production |
| `agents/logist.py` | 442 | ~40 | CRM, доставка, phone_utils | ✅ Production |
| `agents/analyst.py` | 483 | ~28 | CRM | ✅ Production |
| `web/api.py` | 1242 | 22 | FastAPI, CRM, SSE, CSV | ✅ Production |
| `integram_api.py` | 339 | 24 | httpx, auto re-auth | ✅ Production |
| `integram_client.py` | 570 | — | integram_api | ✅ Production |
| `delivery/cdek.py` | 254 | ~10 | httpx, OAuth2 | ✅ Production |
| `delivery/pochta.py` | 269 | ~10 | httpx | ✅ Production |
| `delivery/tracker.py` | 117 | — | CRM, доставка | ✅ Production |
| `integrations/uds.py` | 697 | 28 | httpx, CRM | ✅ Production |
| `knowledge_base.py` | 227 | 16 | FAISS, sentence-transformers | ✅ Production |
| `phone_utils.py` | 60 | 24 | — | ✅ Production |

---

## 11. Потоки данных

### Создание заказа через бота

```mermaid
sequenceDiagram
    participant U as Клиент
    participant B as Бот
    participant L as Логист
    participant CRM as Integram
    participant D as СДЭК/Почта
    participant A as Пчеловод

    U->>B: "Хочу заказать"
    B->>L: start_order(user_id)
    L-->>B: Каталог товаров (inline)
    U->>B: Выбирает товар
    L->>CRM: get_client_by_telegram(user_id)
    CRM-->>L: {name, phone, address}
    L-->>B: Подставить ФИО?
    U->>B: "Да" / новое ФИО
    U->>B: Телефон
    Note over L: validate_phone("+79001234567")
    U->>B: Адрес
    L->>D: calculate(city, weight)
    D-->>L: Стоимость доставки
    L-->>B: Итого: товар + доставка
    U->>B: "Подтвердить"
    L->>CRM: create_order(client, items)
    L->>CRM: add_order_items(order_id, items)
    L->>CRM: recalculate_totals(order_id)
    CRM-->>L: OK
    L-->>B: Заказ ORD-0327 создан
    B->>A: 🔔 Новый заказ (Telegram)
```

### Авто-трекинг доставки

```mermaid
sequenceDiagram
    participant T as OrderTracker
    participant CRM as Integram
    participant D as СДЭК/Почта
    participant C as Клиент

    loop Каждые 2 часа
        T->>CRM: get_orders(status="Отправлен")
        CRM-->>T: [заказы с трек-номерами]
        loop Для каждого заказа
            T->>D: track(tracking_number)
            D-->>T: {status, location, date}
            alt Доставлен
                T->>CRM: update_status("Доставлен")
                T->>CRM: get_client_telegram_id(client_id)
                CRM-->>T: telegram_id
                T->>C: 🔔 "Ваш заказ доставлен!"
            end
        end
    end
```

---

*Анализ проблем: [analysis.md](../analysis.md)*
*План развития: [plan.md](../plan.md)*
