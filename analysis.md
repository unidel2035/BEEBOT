# BEEBOT — Анализ текущего состояния

> **Дата:** 4 апреля 2026 (по итогам фаз 1–5.0 + серия CRM v2 фиксов)
> **Версия:** v2.2
> **Ветка:** fix/v2-singleflight → main (13 PR merged today)

---

## 1. Обзор проекта

BEEBOT — Telegram-помощник + веб-панель управления заказами для «Усадьба Дмитровых».
Многоагентная система на LangGraph с 6 агентами, FAISS-поиском по базе знаний,
двойной CRM-интеграцией (Integram v1 архив + v2 основная) и PWA веб-панелью.

### Масштаб кодовой базы

| Компонент | Файлов | Строк |
|-----------|--------|-------|
| Бот + роутеры | 9 | ~2 200 |
| Агенты (6 шт.) | 6 | 1 290 |
| CRM-клиенты (v1 + v2 + factory) | 5 | 2 800 |
| Веб-панель (backend) | 20 | 2 808 |
| Service Layer (действующий) | 3 | 441 |
| Gift Protocol + SharedContext + AgentSpecs | 5 | ~780 |
| Доставка | 5 | ~1 000 |
| KB + LLM + память | 6 | ~950 |
| DEVBOT | 7 | ~1 150 |
| Frontend (Vue 3, 14 views) | ~30 | ~5 000 |
| Тесты | 39 | 8 715 |
| **Итого** | ~140 | **~23 000** |

---

## 2. Сильные стороны

### Архитектура
- **Многоагентная система** — 6 специализированных агентов с чётким разделением ответственности
- **LangGraph-оркестратор** — классификация intent + маршрутизация
- **Один процесс** — бот и веб-панель в одном asyncio: нет IPC, -400 MiB RAM
- **Graceful degradation** — fallback на статичные данные при недоступности CRM/LLM/туннелей
- **Гибридный KB-поиск** — 70% семантика (FAISS) + 30% стилометрия + keyword-буст из каталога
- **5 голосовых стилей** — «Голос Улья» с разными системными промптами
- **Gift Protocol** — передача SharedContext между агентами (SharedContextStore + CrmAgent + GiftBroker)

### Реализация
- **CRM v2 (ai2o.online)** — новый клиент с 13 методами, JWT-авторизация, 27 тестов
- **Singleflight + кэш** — нет лавины параллельных запросов к CRM (реализовано в #182)
- **OrderService** — единая точка создания заказов (Telegram / UDS / Веб)
- **BackgroundTaskManager** — CrmSnapshot, OrderTracker, UDSPoller, TunnelMonitor, BackupManager
- **Async/await** — полностью асинхронный стек
- **Docker** — multi-stage build, `network_mode: host` на VPS
- **CI/CD** — GitHub Actions (ruff + mypy + bandit + pytest + deploy)

### Функциональность
- **14 страниц веб-панели** (PWA, offline-сборка, SSE, Канбан, drag & drop)
- **DEVBOT** — автономный разработчик через /dev (Claude API + CLI)
- **Авто-трекинг** — СДЭК + Почта России каждые 2 часа
- **UDS-синхронизация** — поллинг каждые 5 мин, catch-up с 01.01.2024
- **Онтология** — 74 симптома + 77+ показаний (Integram → OntologyCache)

---

## 3. Критические проблемы (P0)

### 3.1 Регрессия Service Layer — CRITICAL (только локально)

Девять файлов сервисов удалены локально (`git status: D`), но `startup.py` по-прежнему импортирует их:

```python
# src/startup.py — все эти импорты сломаны локально
from src.services.auth_service import AuthService        # ❌ DELETED
from src.services.analytics_service import AnalyticsService  # ❌ DELETED
from src.services.consult_service import ConsultService   # ❌ DELETED
from src.services.worker_service import WorkerService     # ❌ DELETED
from src.services.delivery_service import DeliveryService # ❌ DELETED
from src.services.dashboard_service import DashboardService  # ❌ DELETED
from src.services.state_store import StateStore           # ❌ DELETED
```

**Статус на production (VPS):** ✅ Работает — `main` содержит все файлы.
**Статус локально:** ❌ ImportError при запуске.
**Причина:** Незавершённая очистка Service Layer — файлы удалены, импорты остались.

**Удалённые сервисы (9 штук):**

| Сервис | Что делал | Кем заменён |
|--------|----------|-------------|
| `auth_service.py` | Проверка ролей admin/worker | Прямые проверки в роутерах |
| `analytics_service.py` | ABC-анализ, отчёты | AnalystAgent + orchestrator |
| `consult_service.py` | KB → LLM консультация | BeebotAgent напрямую |
| `dashboard_service.py` | Статистика дашборда | dashboard.py роутер |
| `delivery_service.py` | Расчёт доставки | delivery/ напрямую |
| `worker_service.py` | Очередь сборки | WorkerAgent in-memory |
| `state_store.py` | Redis состояние | Удалён (Redis не используется) |
| `event_emitter.py` | SSE события | Прямой SSE в api.py |
| `circuit_breaker.py` | Защита CRM | Удалён |

**Действие:** восстановить файлы (git checkout) или убрать импорты из startup.py и Services.

### 3.2 Артефакт merge-конфликта

Файл `src/bot.py.rej` существует в рабочей директории (untracked). Это остаток merge-конфликта — изменения (fsm_edit_router) уже применены в bot.py. Файл можно безопасно удалить.

---

## 4. Серьёзные проблемы (P1)

### 4.1 AnalystAgent — заглушка (56 строк)

`src/agents/analyst.py` — stub. Реальная аналитика в оркестраторе (orchestrator.py). Нет отдельного AnalyticsService — был удалён. Пользователь `/stats` получает результат, но архитектура неправильная.

### 4.2 AdminChatAgent — двойная загрузка CRM

Два пути получения данных:
- **Live-запросы** — 23+ HTTP на сообщение
- **CrmSnapshot** — кэш 5 мин

Оба активны одновременно в зависимости от ситуации. Приводит к непоследовательным данным.

### 4.3 WorkerAgent — состояние в RAM

Очередь сборки заказов хранится в `dict` в памяти. При рестарте бота — потеря очереди. Работники должны заново начинать сборку.

### 4.4 A.7 — production switch не выполнен

Переменная `INTEGRAM_V2=true` ещё не установлена на VPS. Бот и веб-панель используют v1 CRM (ai2o.ru). Несмотря на то что v2 клиент готов и все тесты зелёные.

### 4.5 Тесты для удалённых сервисов

9 тестовых файлов импортируют удалённые сервисы → `ImportError` при `pytest`.

```
tests/test_analytics_service.py   → AnalyticsService (DELETED)
tests/test_dashboard_service.py   → DashboardService (DELETED)
tests/test_auth_service.py        → AuthService (DELETED)
tests/test_consult_service.py     → ConsultService (DELETED)
# и т.д.
```

---

## 5. Конфликты логик

### 5.1 Три пути создания заказа → разная логика уведомлений

| Путь | Файл | NotificationService? | SSE? |
|------|------|----------------------|------|
| Telegram FSM | logist.py → OrderService | ✅ | ✅ |
| Веб-панель | orders.py → OrderService | ✅ | ✅ |
| UDS-поллер | uds.py → OrderService | ✅ | ✅ |

OrderService унифицирован (B.1–B.3 done). Но разные пути имеют разный набор полей клиента.

### 5.2 Orchestrator vs Router — рассыпанная логика

| Intent | Orchestrator? | Где реально? |
|--------|---------------|-------------|
| consult | ✅ BeebotAgent | Orchestrator |
| stats | ✅ AnalystAgent | Orchestrator |
| greeting | ✅ | Orchestrator |
| order | ❌ → END | fsm_order_router |
| edit | ❌ → END | fsm_edit_router |
| track | ❌ → END | bot.py inline |
| inspect | ❌ → END | inspect_router |

4 из 7 интентов → END. Оркестратор классифицирует, но не обрабатывает — роутеры перехватывают раньше. Архитектурно правильно, но не очевидно.

### 5.3 CRM v1 vs v2 — два мира

| | v1 (ai2o.ru) | v2 (ai2o.online) |
|---|---|---|
| Статус | **Используется в production** | Готов, не подключён в production |
| Auth | Cookie-based | JWT |
| Поля | По REQ_ID | По имени колонки |
| Данные | 1924 клиента, 1915 заказов | 85 товаров |
| Клиент | integram_client.py (849 стр.) | integram_v2_client.py (1002 стр.) |
| Тесты | Есть | 27 тестов (#146) |

### 5.4 BeebotAgent vs InspectorAgent — перекрытие KB

Оба используют одну FAISS KB и LLM. Разница: BeebotAgent — одноразовый ответ, InspectorAgent — 3-шаговый диалог. Пользователь, задавая «симптомный» вопрос в общем чате, получает ответ BeebotAgent вместо инспектора.

### 5.5 SharedContext vs AdminChatAgent — двойное хранение истории

`SharedContextStore` хранит историю по user_id. `AdminChatAgent._history` хранит свою историю. При переходе user_id из обычного режима в /admin — контексты не синхронизируются.

### 5.6 EventBus — написан, не используется эффективно

`src/bus.py` (244 строки) — Redis Streams реализованы. `web/bus_handlers.py` — все обработчики выбрасывают `NotImplementedError`. Фактически EventBus не передаёт события между компонентами.

---

## 6. Аудит кода: мусор и технический долг

### Устаревшие / нефункциональные файлы

| Файл | Статус | Проблема |
|------|--------|----------|
| `src/bot.py.rej` | Untracked | Merge-конфликт артефакт, изменения уже в bot.py |
| `src/web/bus_handlers.py` | Active but broken | Все методы → NotImplementedError |
| `src/agents/analyst.py` | Stub | 56 строк, вся логика в orchestrator |

### Удалённые локально, но используемые в startup.py

9 файлов (см. раздел 3.1) — вызывают ImportError при локальном запуске.

### Дублирование логики

| Что | Где дублируется | Объём |
|-----|----------------|-------|
| KB поиск | beebot.py + inspector.py + admin_chat.py | 3 места |
| История диалога | shared_context.py + admin_chat._history | 2 независимых стора |
| CRM-контекст для LLM | admin_chat._get_crm_context + _build_context_from_snapshot | ~180 строк |
| Обработка ошибок CRM | Каждый агент по-своему | 6+ мест |

### Неиспользуемый код

| Компонент | Строк | Причина |
|-----------|-------|---------|
| bus.py EventBus + bus_handlers | ~434 | Не используется в production |
| delivery/base.py | 41 | Абстрактный класс-заглушка |
| integram_api.py (часть методов) | ~200 | v1 методы не используются при v2=true |

---

## 7. Безопасность

| Проблема | Файл | Критичность |
|----------|------|-------------|
| DEVBOT FastAPI без авторизации (allow_origins=["*"]) | devbot/bot.py | Средняя |
| SSE-токен без проверки срока жизни | web/api.py | Низкая |
| Rate limiting 60 req/min для всех эндпоинтов | slowapi | Средняя |
| Доступ к private crm._api | ~~batches.py, clients.py~~ | ✅ Исправлено в #148 |

---

## 8. Инфраструктурные ограничения

| Ограничение | Статус | Решение |
|-------------|--------|---------|
| VPS 2 GB RAM (beebot ~762 MiB) | Работает | Апгрейд до 4 GB при росте |
| Groq блокирует IP VPS | Решено: SSH-туннель → hive:8990 | groq-proxy.service |
| Telegram API блокирует IP VPS | Решено: SOCKS5 → hive:9150 | tg-socks.service |
| hive — SPOF | Groq+TG+DEVBOT на одной машине | Облачный fallback не реализован |
| Squash-мерж → VPS reset | `git reset --hard origin/main` | Задокументировано |
| api.uds.app блокирует VPS | `uds_proxy.py` (hive:8991) | Работает, не задокументировано |
| YouTube блокирует IP | Субтитры скачаны заранее | data/subtitles/ |

---

## 9. Память агентов: текущее состояние и разрывы

| Агент | Диалог (RAM) | Факты (SQLite) | Анамнез (CRM) | CrmSnapshot |
|-------|-------------|----------------|---------------|-------------|
| Консультант | ✅ 5 пар | ✅ | ✅ | — |
| Логист | — | — | — | — |
| Аналитик | — | — | — | — |
| Инспектор | — | — | — | — |
| Ассистент | ✅ 10 пар (своя) | — | — | ✅ |
| Работник | — | — | — | — |
| DEVBOT | — | — | — | — DEV_TASKS/MEMORY/ADVICE |

**Главная проблема:** LangGraph Checkpointer не используется — вся история графа в RAM, теряется при рестарте.

---

## 10. Рейтинг компонентов

| Компонент | Качество | Тесты | Проблемы |
|-----------|---------|-------|----------|
| Knowledge Base | A | B | — |
| LLM Client (Groq) | A | B | — |
| BeebotAgent | A | B | Overlap с Inspector |
| LogistAgent | B | A | — |
| AnalystAgent | C | A | Stub, реальная логика в orchestrator |
| InspectorAgent | B | B | Overlap с Beebot |
| AdminChatAgent | C | B | Двойная загрузка CRM |
| WorkerAgent | B | B | State в RAM |
| IntegramClient v1 | B | A | Устаревает |
| IntegramV2Client | A | A | 27 тестов, singleflight |
| OrderService | A | A | Работает |
| Веб-панель (backend) | B | A | — |
| Веб-панель (frontend) | A | — | PWA, Канбан, offline |
| DEVBOT | B | — | DEVBOT без авторизации API |
| Docker + CI/CD | A | — | ruff+mypy+bandit+pytest+deploy |
| startup.py | D | — | Импортирует удалённые сервисы |

---

## 11. CRM v2 — статус миграции (4 апреля 2026)

Сегодня слиты 13 PR с фиксами CRM v2:

| PR | Что исправлено |
|----|---------------|
| #183 | get_dashboard_stats — правильные поля DashboardStats |
| #182 | Singleflight + кэш get_orders() — нет лавины запросов |
| #180 | Загружать только реальные заказы (с позициями) |
| #178 | Снизить нагрузку при загрузке позиций |
| #177 | Исправить номер заказа и пагинацию REST |
| #176 | _fetch_all_order_ids_rest не включать стр.1 при last_n_pages>0 |
| #174 | Прикрепить позиции к заказам в list_orders |
| #173 | REST-пагинация + parallel objId для заказов и позиций |
| #171 | get_order_items через REST parentId + AI tool fields |
| #169 | Восстановить логин веб-панели при INTEGRAM_V2=true |
| #168 | Исправить схему и статусы Integram v2 |
| #167 | Исправить импорты IntegramV2Client |
| #166 | История изменений — привязка parentId к v2 заказу |

**Следующий шаг (A.7):** установить `INTEGRAM_V2=true` в `.env` на VPS и пересобрать Docker.

---

*Связанные документы: [plan.md](plan.md) | [docs/architecture.md](docs/architecture.md) | [README.md](README.md)*
