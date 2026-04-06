# BEEBOT — Текущее состояние

> Обновляется Tech Writer в конце каждой сессии.
> Это — handover документ для следующей сессии.

---

## Последнее обновление
**Дата:** 2026-04-06
**Сессия:** Проектирование командной инфраструктуры

---

## Активная ветка
`feat/m5-agent-context`

**База:** upstream `alekseymavai/BEEBOT` main (значительно ушёл вперёд с 29.03.2026)

---

## Прогресс по фазам

### Выполнено (M1–M4) ✅
- **M1** — LangGraph Checkpointer (SqliteSaver, `data/checkpoints.db`)
- **M2** — agent_id namespace в UserMemory (ALTER TABLE user_memory ADD COLUMN agent_id)
- **M3** — таблица episodes в UserMemory
- **M4** — MemoryService — единый API памяти для агентов

### В процессе
- **M5** — AgentContext: оркестратор и admin используют MemoryService
  Статус: коммит `297a5ae` сделан, нужна проверка + деплой

### Критические задачи (Fix)
- **Fix-1** 🔴 — 9 файлов в `src/services/` удалены локально (git status: D)
  `startup.py` импортирует их → ImportError при запуске
  Действие: `git checkout HEAD -- src/services/`

- **Fix-2** 🟡 — Production switch `INTEGRAM_V2=true` на VPS ещё не включён
  Бот работает на v1 CRM (ai2o.ru), v2 готов

### Следующие задачи (из plan.md)
- **AN.1** — Восстановить AnalyticsService (перенесён в services/)
- **D.1–D.6** — Пасечный дневник (новая фича)
- **O.1–O.3** — Offline PWA активация

---

## Что нельзя трогать прямо сейчас

```
❌ НЕ git pull на VPS — только git reset --hard origin/main
❌ НЕ трогать .env на VPS без явного указания Андрея
❌ НЕ запускать pytest без Fix-1 (будет ImportError)
❌ НЕ пушить в upstream напрямую — только через fork unidel2035
❌ НЕ использовать git add -A — только конкретные файлы
```

---

## Состояние upstream vs локально

Upstream `alekseymavai/BEEBOT` main содержит изменения которых нет в CLAUDE.md:
- CRM v2 (`integram_v2_client.py`, `integram_v2_constants.py`, `crm_factory.py`)
- `startup.py` — единая точка инициализации сервисов (335 строк)
- `src/routers/` — 7 роутеров (bot.py больше не монолит, теперь 196 строк)
- `src/services/` — OrderService, NotificationService, AnalyticsService
- `src/shared_context.py`, `src/gift_protocol.py`
- Redis 7 в docker-compose (LangGraph checkpointer)
- `deps.py` — dependency injection для FastAPI
- CI/CD обновлён: ruff + mypy + bandit + pytest

**CLAUDE.md устарел** — описывает архитектуру на 29.03.2026 (монолит bot.py 1899 строк).
Нужно обновить после синхронизации с upstream.

---

## Инфраструктура hive (локальная машина)

| Сервис | Порт | Статус |
|--------|------|--------|
| groq-proxy | 8990 | должен работать |
| groq-tunnel | SSH | должен работать |
| tg-socks | 9150 | должен работать |
| devbot | 8091 | должен работать |

Проверка: `systemctl status groq-proxy groq-tunnel tg-socks`

---

## Что было сделано в этой сессии (2026-04-06)

1. Создана инфраструктура памяти команды:
   - `docs/memory/decisions.md` — 10 ADR (архитектурных решений)
   - `docs/memory/fragile_zones.md` — хрупкие зоны кода с уровнями риска
2. Написаны все 9 договоров агентов в `docs/agents/`:
   - product_owner, scout, architect, backend_dev, frontend_dev
   - qa, security, devops, tech_writer
3. Обновлён `docs/team.md` — статусы агентов → ✅ готов
4. Обновлён `docs/execution_prompt.md` — добавлены ссылки на memory/

### Что ещё не сделано
- Fix-1 не выполнен (src/services/ удалены локально → ImportError)
- CLAUDE.md не обновлён (нужна синхронизация с upstream)
- Fix-2 не выполнен (INTEGRAM_V2=true на VPS)
