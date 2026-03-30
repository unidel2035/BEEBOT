# BEEBOT — План развития

> **Дата:** 30 марта 2026
> **Основан на:** [analysis.md](analysis.md) · [docs/architecture.md](docs/architecture.md)
> **Ориентир архитектуры:** Gift Protocol + dronedoc2026 AgentBus + Agent Card
>
> Фазы 8–12 переработаны. Старые приоритеты (апгрейд VPS, перенос прокси) сняты —
> beebot занимает 193 MiB после PR #109, RAM стабильна.

---

## Фазы 0–7: Завершены ✅

| Фазы | Содержание | Статус |
|------|-----------|--------|
| 0–2 | Стабилизация, качество кода, функциональность | ✅ |
| 3 | LLM-ассистент, память, онтология, пагинация | ✅ 25.03.2026 |
| 4 | История статусов, партии, роутеры, DEVBOT-таблицы | ✅ 27.03.2026 |
| 5 | WorkerAgent — режим сборки заказов | ✅ 29.03.2026 |
| 6 | CrmSnapshot — кэш CRM, UDS catch-up | ✅ 29.03.2026 |
| 7 | DEVBOT — автономный разработчик (MVP) | ✅ 29.03.2026 |

---

## Синхронизация репозитория и железа

> **Правило:** после каждого squash-мержа PR — обязательная синхронизация.
> `git pull` на VPS не работает после squash — только `reset --hard`.

### Текущее состояние (30.03.2026)

| Место | Статус | Последний коммит |
|-------|--------|-----------------|
| upstream/main | ✅ актуален | PR #111 docs: эволюция архитектуры |
| hive (локально) | ⚠️ отстаёт | ветка docs-claude-md, нужен reset |
| VPS | ⚠️ отстаёт | нужен reset + pull |

### Процедура синхронизации (выполнять после каждого PR)

```bash
# 1. hive — сбросить на main
git fetch upstream main
git reset --hard upstream/main

# 2. VPS — сбросить на main
ssh ai-agent@185.233.200.13 "cd /home/ai-agent/BEEBOT && git fetch origin main && git reset --hard origin/main"

# 3. VPS — пересборка (если изменился Python-код)
ssh ai-agent@185.233.200.13 "cd /home/ai-agent/BEEBOT && docker compose up -d --build --force-recreate beebot"

# 4. VPS — только документы (git pull без пересборки)
ssh ai-agent@185.233.200.13 "cd /home/ai-agent/BEEBOT && git fetch origin main && git reset --hard origin/main"
```

### ⚠️ Нужно сделать сейчас

- [ ] hive: `git fetch upstream main && git reset --hard upstream/main`
- [ ] VPS: синхронизировать с main (PR #111)

---

## Фаза 8: Качество и стабильность (P1)

> Актуальна. Выполняется до начала Gift Protocol — иначе рефакторить монолит.

### 8.1 Разбить bot.py на Router-модули

**Проблема:** `src/bot.py` 1 899 строк — все роли в одном файле.

```
src/routers/
├── user.py       # /start, /help, /products, /ask, /voice, /cancel
├── worker.py     # worker:queue, worker:order:*, worker:take:*, worker:done:*
├── admin.py      # /admin, /stats, /faq, /yt_check, /yt_update, /dev
└── fsm_order.py  # OrderFSM + InspectFSM хэндлеры
```

- [ ] Создать `src/routers/` с 4 файлами
- [ ] Перенести хэндлеры из bot.py в соответствующие роутеры
- [ ] bot.py → только startup/shutdown + `dp.include_router()`

### 8.2 Убрать дублирование AdminChatAgent

**Проблема:** `_get_crm_context()` и `_build_context_from_snapshot()` ~330 строк одинакового кода.

- [ ] Выделить `_format_context(orders, products, clients) → str`
- [ ] Оба метода → загружают данные → вызывают `_format_context`

### 8.3 Добавить `inspect` в оркестратор

- [ ] Добавить `inspect` в `_INTENT_SYSTEM` (orchestrator.py)
- [ ] Фразы для `_fast_classify`: «осмотр улья», «диагностика», «осмотри»
- [ ] Нода `inspector` в LangGraph граф → passthrough → bot.py запускает InspectFSM

### 8.4 UDS: сопоставление товаров по SKU

**Проблема:** `_build_order_items()` ищет по имени → `product_id=0` у многих позиций.

- [ ] `integram_client`: добавить `get_product_by_sku(sku_uds: str) → Product | None`
- [ ] `_build_order_items()`: сначала по `good["sku"]`, fallback — по имени
- [ ] Синхронизировать `sku_uds` в Integram для всех 76 товаров

---

## Фаза 9: Gift Protocol (P1 — новая архитектура)

> Три шага эволюции: не переписывание, а наслоение поверх существующего кода.
> Подробнее: [docs/architecture.md §10](docs/architecture.md)

### 9.1 SharedContext — рабочая память (шаг 1)

**Что:** единый `dict` + TTL на user_id. Заменяет `_dialog_states` + `_histories` + разрозненные факты.

```python
# src/shared_context.py — ~100 строк
@dataclass
class UserContext:
    user_id: int
    dialog_history: list[dict]     # последние 5 пар
    active_order: dict | None      # текущий заказ в FSM
    health_facts: list[str]        # из SQLite + Integram
    interests: list[str]           # упомянутые продукты
    last_products_hint: list[str]  # из онтологии
    updated_at: float
```

- [ ] Создать `src/shared_context.py`
- [ ] Перенести `_dialog_states` и `_histories` из orchestrator.py → SharedContext
- [ ] Передавать SharedContext в каждый агент вместо разрозненных параметров

### 9.2 CrmAgent — единственный владелец CRM (шаг 2)

**Проблема:** IntegramClient вызывается из 10+ мест напрямую.
**Решение:** один класс `CrmAgent`, все остальные идут только через него.

```python
# src/crm_agent.py — ~150 строк
class CrmAgent:
    """Единственный владелец CRM-домена. Все вызовы к Integram — только через него."""
    async def get_orders(self, filters=None) → list[Order]: ...
    async def create_order(self, order_data: dict) → Order: ...
    async def update_status(self, order_id: int, status: str) → None: ...
    async def add_health_fact(self, user_id: int, fact: str) → None: ...
    async def get_client_history(self, user_id: int) → ClientHistory: ...
```

- [ ] Создать `src/crm_agent.py` как обёртку над `integram_client.py`
- [ ] Перенаправить все 10+ прямых вызовов IntegramClient через CrmAgent
- [ ] Integram недоступен → CrmAgent: DEFERRED + retry очередь (asyncio.Queue)

### 9.3 Gift TypedDict + GiftBroker (шаг 3)

**Что:** `Gift` как TypedDict на 5 полей. `GiftBroker` заменяет `Orchestrator._build_graph()`.
LangGraph остаётся внутри — просто получает обогащённый контекст из SharedContext.

```python
# src/gift_protocol.py — ~200 строк
class Gift(TypedDict):
    giver: str
    receiver: str
    content: dict
    context: dict          # из SharedContext — уже обогащённый
    telos: str             # зачем этот дар
    anamnesis: list[dict]  # прошлые значимые дары (A3)
    freedom: str           # ACCEPTED | DEFERRED | DECLINED

class GiftBroker:
    """Знает SharedContext. Матчит потребности. Доставляет дары."""
    async def send(self, gift: Gift) → Gift: ...
    async def defer(self, gift: Gift, ttl: int) → None: ...
```

- [ ] Создать `src/gift_protocol.py`
- [ ] GiftBroker как надстройка над Orchestrator (не замена сразу)
- [ ] Логировать каждый Gift → audit log = полная история события

### 9.4 WorkerAgent: inbox + DEFERRED

**Проблема:** чеклист теряется при рестарте; нет логики «занят → отложить».

- [ ] WorkerAgent: `state: Literal["idle", "busy"]` + `inbox: asyncio.Queue`
- [ ] `receive(gift) → ACCEPTED / DEFERRED` — если занят, кладёт в inbox
- [ ] Чеклист → SharedContext → CrmAgent (не RAM dict)
- [ ] Broker доставляет отложенный Gift когда Worker освобождается

### 9.5 AGENT_SPECS в Integram (из dronedoc2026)

> Agent Card — агент декларирует что умеет. Александр меняет поведение без деплоя.

**Что:** таблица `AGENT_SPECS` в Integram: agent_id, system_prompt, skills, triggers, voice_style.

- [ ] Создать таблицу AGENT_SPECS в Integram (через crm_constants.py)
- [ ] При старте бота: загрузить спецификации агентов из Integram
- [ ] BeebotAgent читает system_prompt из AGENT_SPECS (не из кода)
- [ ] Команда `/agent_config <agent> <field> <value>` для пчеловода

---

## Фаза 10: Память и персонализация (P2)

### 10.1 AnamnesisCache — эпизодическая память (A3)

> A3 Gift Ontology: прошлые дары со-присутствуют в новом.
> Broker включает `anamnesis[]` в каждый Gift — агент получает контекст истории.

- [ ] `src/anamnesis.py`: кэш значимых прошлых взаимодействий на user_id
- [ ] Источники: SQLite (факты) + CrmAgent (история заказов) + FAQ (темы интереса)
- [ ] GiftBroker собирает anamnesis автоматически перед отправкой Gift Beebot/Logist
- [ ] Logist: если есть история заказов → предзаполнять адрес, пропускать шаги

### 10.2 extract_fact — устранение ложных срабатываний

**Проблема:** «у меня нет язвы» → сохраняется как health-факт «язва».

- [ ] Добавить детектор отрицаний в `memory.py:extract_fact()`
- [ ] Паттерны: «нет», «не было», «не страдаю», «не болею» → skip

### 10.3 Персонализация: «Вы уже брали»

- [ ] Консультант: при consult — проверить историю заказов через CrmAgent
- [ ] Если купил X → рекомендовать Y из онтологии
- [ ] «Хотите повторить заказ от 15 марта?» при ключевых словах

### 10.4 YouTube-комментарии в KB

- [ ] Фильтровать ответы Александра из комментариев к видео
- [ ] Добавить в FAISS как отдельный источник (высокий вес — прямая речь)

---

## Фаза 11: Интерфейсы и экосистема (P2)

### 11.1 Событийные интерфейсы (из dronedoc2026)

> Идея: UI под роль + контекст + события. Не жёсткий `if WORKER_CHAT_IDS`.
> GiftBroker решает что показать какому пользователю — через Agent Card.

- [ ] Каждый агент декларирует `triggers: list[str]` в AGENT_SPECS
- [ ] GiftBroker при `/start` выбирает интерфейс по контексту, а не по enum роли
- [ ] Рабочий завершил все заказы → бот предлагает переключиться в режим клиента

### 11.2 AgentBus — регистрация BEEBOT

- [ ] `POST /api/agent-bus/register` (dronedoc2026, порт 8081) с Agent Card BEEBOT
- [ ] Хэндлер входящих: `/api/agent-bus/inbox/beebot`
- [ ] Экспортировать инструменты: KB-поиск, статус заказа, создать заказ
- [ ] Heartbeat каждые 30 сек

### 11.3 PDF-отчёты и аналитика

- [ ] Экспорт PDF: выручка за период, топ товаров, ABC-анализ клиентов
- [ ] Прогноз спроса на следующий месяц через LLM + статистика
- [ ] Алерт при низком остатке (<5 шт.) → уведомление пчеловоду

---

## Фаза 12: Инфраструктура и надёжность (P3)

> ⚠️ Апгрейд VPS снят с приоритетов: beebot = 193 MiB, RAM стабильна.
> hive SPOF: мониторинг + fallback важнее переноса.

### 12.1 Fallback при потере hive-туннеля

**Цепочка:** Groq API → таймаут → упрощённый ответ без LLM (FAQ из кэша).

- [ ] Детектор разрыва туннеля: ping hive каждые 60 сек из VPS
- [ ] При разрыве: алерт пчеловоду в Telegram
- [ ] Fallback-ответ консультанта: топ-5 FAQ без LLM

### 12.2 Резервное копирование

- [ ] Ежедневный бэкап `data/memory.db` на Yandex Disk
- [ ] Еженедельный экспорт CRM → CSV через `CrmAgent.export()`
- [ ] Backup `faq_queries.json`

### 12.3 DEVBOT авторизация

**Проблема:** FastAPI на 8091 без авторизации (`allow_origins=["*"]`).

- [ ] Добавить Bearer-токен в DEVBOT_API_URL
- [ ] Валидация в FastAPI middleware devbot/bot.py

### 12.4 SSL + домен веб-панели

- [ ] Nginx reverse proxy с Let's Encrypt SSL
- [ ] Домен → https://
- [ ] JWT в httpOnly cookie (убрать XSS-риск)

### 12.5 Платёжная интеграция

- [ ] YooKassa или СБП — онлайн-оплата в Telegram
- [ ] Авто-смена статуса после подтверждения оплаты
- [ ] Webhook для уведомлений платёжного шлюза

---

## Что снято с плана (было актуально — стало неактуально)

| Было | Причина снятия |
|------|---------------|
| Апгрейд VPS до 4 GB (10.5) | beebot = 193 MiB после PR#109, RAM в норме |
| Перенос Groq-прокси на VPS (10.1 вариант A) | RAM освободилась, нет смысла усложнять |
| Стойкость чеклиста → SQLite (9.4 старый) | Заменяется: чеклист → SharedContext → CrmAgent |
| Советы DEV_ADVICE в промпте (9.3 старый) | Поглощается: AGENT_SPECS в Integram (9.5 новый) |

---

## Сводная таблица приоритетов

| П | Задача | Фаза | Сложность | Синхронизация |
|---|--------|------|-----------|---------------|
| **P0** | Синхронизация hive + VPS с main | — | Мин | hive reset + VPS reset |
| **P1** | Разбить bot.py на Router-модули | 8.1 | Средняя | PR → squash → VPS rebuild |
| **P1** | Убрать дублирование AdminChatAgent | 8.2 | Низкая | PR → squash → VPS rebuild |
| **P1** | Inspect в оркестраторе | 8.3 | Низкая | PR → squash → VPS rebuild |
| **P1** | UDS SKU-сопоставление | 8.4 | Средняя | PR → squash → VPS rebuild |
| **P1** | SharedContext (рабочая память) | 9.1 | Низкая | PR → squash → VPS rebuild |
| **P1** | CrmAgent (единый владелец) | 9.2 | Средняя | PR → squash → VPS rebuild |
| **P1** | Gift TypedDict + GiftBroker | 9.3 | Средняя | PR → squash → VPS rebuild |
| **P2** | WorkerAgent inbox + DEFERRED | 9.4 | Средняя | PR → squash → VPS rebuild |
| **P2** | AGENT_SPECS в Integram | 9.5 | Средняя | PR → squash → без rebuild |
| **P2** | AnamnesisCache (эпизодическая память) | 10.1 | Средняя | PR → squash → VPS rebuild |
| **P2** | extract_fact отрицания | 10.2 | Низкая | PR → squash → VPS rebuild |
| **P2** | Персонализация «Вы уже брали» | 10.3 | Средняя | PR → squash → VPS rebuild |
| **P2** | YouTube-комментарии в KB | 10.4 | Средняя | PR → squash → VPS rebuild |
| **P2** | Событийные интерфейсы | 11.1 | Высокая | PR → squash → VPS rebuild |
| **P2** | AgentBus регистрация | 11.2 | Средняя | PR → squash → без rebuild |
| **P2** | PDF-отчёты | 11.3 | Средняя | PR → squash → VPS rebuild |
| **P3** | Fallback при потере hive-туннеля | 12.1 | Средняя | PR → squash → VPS rebuild |
| **P3** | Резервное копирование | 12.2 | Низкая | systemd + cron на VPS |
| **P3** | DEVBOT авторизация | 12.3 | Низкая | PR → squash → hive restart |
| **P3** | SSL + домен | 12.4 | Средняя | VPS nginx config |
| **P3** | Платёжная интеграция | 12.5 | Высокая | PR → squash → VPS rebuild |

---

## Принципы (из dronedoc2026, применимые к BEEBOT)

1. **ИИ — инструмент, не судья.** Ни один агент не принимает решений без пчеловода. Все выводы — рекомендации.
2. **Минимально необходимый доступ.** CrmAgent — единственный кто видит CRM. Остальные — через Gift.
3. **Прозрачность каждого вывода.** Beebot даёт ссылку на источник знания (чанк + видео/документ).
4. **Агент не выходит за роль.** Консультант не создаёт заказы. Логист не консультирует.
5. **Свобода агента — условие дара (A5).** DEFERRED — не ошибка, а корректный ответ.

---

*Связанные документы: [analysis.md](analysis.md) · [docs/architecture.md](docs/architecture.md)*
