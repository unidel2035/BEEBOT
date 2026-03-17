# BEEBOT — Архитектурные диаграммы

> Версия: 16 марта 2026

---

## 1. Общая архитектура системы

```mermaid
graph TB
    subgraph Пользователи
        TG[Telegram]
        WEB[Веб-панель<br/>PWA]
    end

    subgraph VPS["VPS (Docker)"]
        BOT[Telegram-бот<br/>aiogram 3]
        ORCH[Оркестратор<br/>LangGraph]
        BEEBOT_A[Агент Консультант]
        LOGIST[Агент Логист]
        ANALYST[Агент Аналитик]
        API[FastAPI<br/>Веб-API]
        FAISS[FAISS<br/>410 чанков]
    end

    subgraph Внешние сервисы
        GROQ[Groq API<br/>llama-3.3-70b]
        CRM[Integram CRM<br/>ai2o.ru/bibot]
        CDEK[СДЭК API]
        POCHTA[Почта России API]
    end

    subgraph HIVE["Hive (локальная)"]
        PROXY[groq-proxy<br/>порт 8990]
        TUNNEL[SSH-туннель]
    end

    TG --> BOT
    WEB --> API
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
    TUNNEL --> PROXY --> GROQ
```

---

## 2. Поток обработки сообщения

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant B as Telegram-бот
    participant O as Оркестратор
    participant KB as FAISS
    participant LLM as Groq LLM

    U->>B: Текстовое сообщение
    B->>O: classify(message)
    O->>LLM: Определить интент (~100 токенов)
    LLM-->>O: "consult" | "order" | "stats" | ...

    alt consult
        O->>KB: search(query, top_k=5)
        KB-->>O: 5 чанков контекста
        O->>LLM: generate(context + system_prompt)
        LLM-->>O: Ответ в стиле автора
        O-->>B: Текст + кнопки [PDF] [Каталог]
    else order
        O->>B: Запуск FSM логиста
        Note over B: 7 шагов оформления
    else stats
        O->>B: Проверка ADMIN_CHAT_ID
        O->>KB: Аналитический запрос к CRM
    end

    B-->>U: Ответ
```

---

## 3. Гибридный поиск в базе знаний

```mermaid
graph LR
    Q[Запрос пользователя] --> EMB[Эмбеддинг<br/>MiniLM-L12-v2]

    EMB --> SEM[Семантический поиск<br/>FAISS cosine<br/>Вес: 70%]
    EMB --> STY[Стилометрия<br/>длина предложений,<br/>слов, пунктуация<br/>Вес: 30%]

    SEM --> MERGE[Объединение скоров]
    STY --> MERGE

    Q --> KW[Keyword-буст<br/>прополис → Прополис.txt<br/>перга → Перга.txt]
    KW --> MERGE

    MERGE --> TOP5[Топ-5 чанков]
    TOP5 --> LLM[LLM генерация ответа]
```

**Источники данных:**

| Тип | Кол-во | Описание |
|-----|--------|----------|
| PDF-инструкции | 19 | Перга, прополис, ПЖВМ, гомогенат и др. |
| Тексты | 21 | Очищенные выдержки из PDF |
| YouTube | 26 | Расшифровки видео с канала @a.dmitrov |

---

## 4. FSM оформления заказа (Логист)

```mermaid
stateDiagram-v2
    [*] --> ВыборТовара: "Хочу заказать"
    ВыборТовара --> ФИО: Товар выбран
    ФИО --> Телефон: ФИО введено
    Телефон --> Адрес: Телефон введён
    Адрес --> Доставка: Адрес введён
    Доставка --> Подтверждение: Способ выбран
    Подтверждение --> СозданиеЗаказа: [Подтвердить]
    Подтверждение --> [*]: [Отменить]
    СозданиеЗаказа --> УведомлениеАдмину
    УведомлениеАдмину --> [*]

    note right of ВыборТовара
        Каталог из CRM
        56 товаров
    end note

    note right of ФИО
        Авто-подстановка
        по Telegram ID
    end note

    note right of Доставка
        СДЭК: ~350₽+
        Почта: ~250₽+
        Самовывоз: 0₽
    end note

    note left of Подтверждение
        Таймаут: 15 мин
    end note
```

---

## 5. Жизненный цикл заказа

```mermaid
stateDiagram-v2
    [*] --> Новый: Заказ создан
    Новый --> Подтверждён: Пчеловод подтвердил
    Подтверждён --> ВСборке: Взят в сборку
    ВСборке --> Отправлен: Трек-номер введён
    Отправлен --> Доставлен: Получен клиентом
    Новый --> Отменён: На любом этапе
    Подтверждён --> Отменён
    ВСборке --> Отменён

    note right of Подтверждён
        PWA Сборка:
        видит заказ
    end note

    note right of Отправлен
        Клиент получает
        трек-номер
    end note
```

---

## 6. Инфраструктура и деплой

```mermaid
graph TB
    subgraph VPS["VPS 185.233.200.13"]
        subgraph Docker
            C1[beebot<br/>Telegram-бот<br/>network_mode: host]
            C2[beebot-web<br/>FastAPI + Vue PWA<br/>порт 8088→8080]
        end
        VOL1[(data/processed<br/>FAISS индекс)]
        VOL2[(data/subtitles)]
    end

    subgraph Hive["Hive (локальная машина)"]
        GP[groq-proxy.service<br/>порт 8990]
        GT[groq-tunnel.service<br/>SSH auto-restart]
    end

    subgraph External["Внешние"]
        GROQ[api.groq.com]
        TGAPI[api.telegram.org]
        ICRM[ai2o.ru<br/>Integram CRM]
        GH[GitHub<br/>alekseymavai/BEEBOT]
    end

    C1 --> TGAPI
    C1 --> ICRM
    C1 -.->|SSH-туннель 8990| GT
    GT -.->|localhost:8990| GP
    GP --> GROQ
    C2 --> ICRM
    C1 --- VOL1
    C1 --- VOL2
    GH -->|git pull| VPS
```

---

## 7. Веб-панель (PWA)

```mermaid
graph LR
    subgraph Frontend["Vue 3 + PrimeVue"]
        DASH[Дашборд<br/>графики, статистика]
        ORD[Заказы<br/>список, детали, создание]
        CLI[Клиенты<br/>список, карточка]
        PROD[Товары<br/>каталог, CRUD]
        PACK[Сборка<br/>PWA терминал]
        STOCK[Склад<br/>PWA терминал]
        JOUR[Журнал<br/>по месяцам]
    end

    subgraph PWA["PWA / Offline"]
        SW[Service Worker<br/>кэш статики]
        IDB[IndexedDB<br/>кэш API + sync queue]
    end

    subgraph Backend["FastAPI"]
        AUTH[JWT Auth]
        APIO[/api/orders]
        APIC[/api/clients]
        APIP[/api/products]
        APID[/api/dashboard]
    end

    DASH --> APID
    ORD --> APIO
    CLI --> APIC
    PROD --> APIP
    PACK --> APIO
    STOCK --> APIP
    PACK -.-> IDB
    STOCK -.-> IDB
    Frontend --> AUTH
    AUTH --> Backend
```

---

## 8. Сравнение модулей

| Модуль | Строк кода | Зависимости | Состояние |
|--------|-----------|-------------|-----------|
| `bot.py` | ~900 | aiogram, LangGraph | Production, работает |
| `orchestrator.py` | ~250 | LangGraph, Groq | Production |
| `agents/beebot.py` | ~150 | FAISS, Groq | Production |
| `agents/logist.py` | ~200 | CRM, доставка | Beta (нет записи в CRM) |
| `agents/analyst.py` | ~180 | CRM | Beta |
| `integram_api.py` | ~400 | httpx | Production |
| `integram_client.py` | ~300 | httpx | Дубликат integram_api |
| `web/api.py` | ~910 | FastAPI, CRM | Production |
| `delivery/cdek.py` | ~100 | httpx | Заглушка (hardcoded) |
| `delivery/pochta.py` | ~80 | httpx | Заглушка (hardcoded) |
| `integrations/uds.py` | ~350 | httpx | Нерабочий (баг) |
| `knowledge_base.py` | ~200 | FAISS, transformers | Production |
| `web/server.py` | ~80 | starlette | Production, PWA |

---

*Анализ проблем: [analysis.md](../analysis.md)*
*План развития: [plan.md](../plan.md)*
