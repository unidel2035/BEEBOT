# BEEBOT — Промт для выполнения plan.md

> Этот файл — инструкция для Claude при выполнении задач из plan.md.
> Используй его в начале каждой рабочей сессии.

---

## Контекст сессии (читать перед началом работы)

```
Проект: BEEBOT — Telegram-бот + веб-панель для «Усадьба Дмитровых»
Локально: /home/hive/BEEBOT/
VPS: ssh ai-agent@185.233.200.13 → /home/ai-agent/BEEBOT/
GitHub upstream: alekseymavai/BEEBOT (push через fork unidel2035/BEEBOT)
Деплой: squash-мерж PR → git reset --hard origin/main на VPS → docker compose up -d --build
Бот на VPS: docker logs --tail 30 beebot
```

**Обязательно в начале сессии:**
1. Прочитать `docs/memory/MEMORY.md` — индекс памяти команды
2. Прочитать `docs/memory/state.md` — текущее состояние, что нельзя трогать
3. Прочитать `plan.md` — найти первую незавершённую задачу
4. Прочитать `analysis.md` — понять контекст и риски
5. Прочитать файлы, которые будут изменяться (`Read` перед `Edit`)
6. Проверить текущую ветку: `git status && git branch`

**Документация команды:**
- `docs/team.md` — состав команды, пайплайн, роли
- `docs/agents/<role>.md` — договор каждого агента (Scout→Architect→Dev→QA→Security→DevOps→TechWriter)
- `docs/memory/antipatterns.md` — что нельзя делать и почему
- `docs/memory/fragile_zones.md` — хрупкие файлы с повышенным риском
- `docs/memory/decisions.md` — принятые архитектурные решения (ADR)

---

## Системный промт выполнения

Ты — опытный Python-разработчик, работающий над проектом BEEBOT.
Твоя задача: выполнять задачи из `plan.md` **по одной**, соблюдая следующий алгоритм.

### Алгоритм выполнения одной задачи

```
1. ВЫБРАТЬ задачу
   → Найти в plan.md первую задачу без ✅
   → Сообщить: "Начинаю задачу [ID]: [название]"

2. ПОНЯТЬ задачу
   → Прочитать все файлы, которые будут затронуты
   → Найти аналогичные паттерны в проекте
   → Убедиться что понимаешь что делать и почему

3. НАПИСАТЬ ТЕСТЫ (test-first)
   → Определить: какой тест докажет что задача выполнена?
   → Написать тест в tests/test_*.py
   → Убедиться что тест ПАДАЕТ (красный) — он проверяет несуществующее

4. НАПИСАТЬ КОД
   → Сделать минимальное изменение для прохождения теста
   → Не добавлять лишнего: только то что нужно для задачи
   → Не трогать код вне scope задачи

5. ПРОВЕРИТЬ
   → Запустить тесты: pytest tests/test_[изменённый_файл].py -v
   → Все тесты зелёные (включая старые)
   → Запустить ruff check src/ — нет ошибок

6. ЗАКОММИТИТЬ
   → Один коммит = одна задача
   → Формат: feat/fix/refactor(scope): описание
   → Обновить отметку ✅ в plan.md

7. ЗАДЕПЛОИТЬ
   → gh auth switch -u unidel2035 && gh auth setup-git
   → git push origin <branch>
   → gh pr create --repo alekseymavai/BEEBOT ...
   → gh pr merge N --repo alekseymavai/BEEBOT --squash
   → ssh ai-agent@185.233.200.13 "cd /home/ai-agent/BEEBOT && git fetch origin main && git reset --hard origin/main"
   → docker compose up -d --build --force-recreate beebot (если Python код)
   → Проверить логи: docker logs --tail 30 beebot
   → gh auth switch -u gaveron18

8. ПОДТВЕРДИТЬ
   → Сообщить: "Задача [ID] выполнена ✅. Следующая: [ID+1]"
   → Спросить Андрея: продолжать или остановиться?
```

---

## Правила работы с кодом

### Перед изменением файла
```
- ВСЕГДА читать файл полностью (Read) перед Edit
- НИКОГДА не угадывать содержимое файла
- Проверить аналогичные паттерны: как сделано в похожих файлах?
```

### Тесты
```
- Файл тестов: tests/test_<модуль>.py
- Запуск: pytest tests/test_X.py -v
- Все старые тесты должны оставаться зелёными
- Новый тест должен сначала упасть, потом пройти
- Мок CRM через AsyncMock (см. test_integram_v2_client.py как пример)
```

### Git workflow
```
- Ветка: feat/<task-id>-<short-description>
- Коммит: feat(scope): краткое описание на русском
- PR: через fork unidel2035/BEEBOT → alekseymavai/BEEBOT
- Мерж: squash (один коммит на задачу)
- VPS: git reset --hard origin/main (НЕ pull!)
- Docker rebuild: только если изменён Python-код
- Frontend rebuild: только если изменён Vue-код (npm run build в web/)
```

### Что НЕ делать
```
- НЕ трогать файлы вне scope задачи
- НЕ делать "пока здесь — исправлю ещё вот это"
- НЕ пропускать тесты ("тут и так очевидно")
- НЕ деплоить без зелёных тестов
- НЕ пушить в upstream напрямую (только через fork)
- НЕ использовать git pull на VPS (только reset --hard)
- НЕ трогать .env на VPS без явного указания
```

---

## Контрольный список перед деплоем

```
□ pytest — все тесты зелёные
□ ruff check src/ — нет ошибок lint
□ git diff --staged — только нужные файлы
□ plan.md обновлён (✅ на выполненной задаче)
□ analysis.md обновлён если изменилась архитектура
□ Коммит-сообщение информативно
□ PR создан через fork unidel2035
□ VPS синхронизирован
□ docker logs — нет ошибок запуска
```

---

## Текущие задачи (актуально на 04.04.2026)

### P0 — Немедленно

**Fix-1: Восстановить локальное dev-окружение**
```
Проблема: 9 файлов в src/services/ удалены локально (git status: D)
          startup.py импортирует их → ImportError при запуске
Файлы: startup.py, src/services/
Действие:
  git checkout HEAD -- src/services/
  python -c "from src.startup import create_services; print('OK')"
Тест: pytest tests/ — нет ImportError
```

**Fix-2: A.7 — Production switch INTEGRAM_V2=true**
```
Проблема: бот работает на v1 CRM (ai2o.ru), v2 готов но не включён
Действие:
  # Проверить текущий .env на VPS
  ssh ai-agent@185.233.200.13 "grep INTEGRAM_V2 /home/ai-agent/BEEBOT/.env"
  # Включить v2
  ssh ai-agent@185.233.200.13 "sed -i 's/INTEGRAM_V2=false/INTEGRAM_V2=true/' /home/ai-agent/BEEBOT/.env"
  # Пересобрать
  ssh ai-agent@185.233.200.13 "cd /home/ai-agent/BEEBOT && docker compose up -d --build --force-recreate beebot"
  # Проверить
  ssh ai-agent@185.233.200.13 "docker logs --tail 30 beebot"
Критерий: в логах "Integram CRM v2 подключена", веб-панель показывает товары
```

### P1 — Эта неделя

**M.1: LangGraph Checkpointer**
```
Файлы: src/orchestrator.py
Цель: персистентная история диалога (переживает рестарт)
Паттерн:
  from langgraph.checkpoint.sqlite import SqliteSaver
  checkpointer = SqliteSaver.from_conn_string("data/checkpoints.db")
  graph = builder.compile(checkpointer=checkpointer)
Тест: tests/test_orchestrator.py — история сохраняется между вызовами
```

**M.2: agent_id namespace в UserMemory**
```
Файлы: src/memory.py, tests/test_memory.py
Цель: каждый агент видит только свои факты
Изменение: ALTER TABLE user_memory ADD COLUMN agent_id TEXT DEFAULT 'global'
           Обновить get_facts(user_id, agent_id=None) — None = все агенты
```

**AN.1: Восстановить AnalyticsService**
```
Файлы: src/services/analytics_service.py (восстановить из git history)
       src/agents/analyst.py (переключить на сервис)
Цель: убрать бизнес-логику из агента в сервис
Паттерн: git show HEAD~N:src/services/analytics_service.py
```

### P2 — Следующий спринт

**D.1-D.6: Пасечный дневник**
```
Новые файлы: src/routers/diary.py, web/src/views/DiaryView.vue
CRM: integram_v2_constants.py — новая таблица «Осмотры»
Бот: /diary FSM (дата → улей → наблюдение → CRM)
```

**O.1-O.3: Offline PWA**
```
Файлы: web/src/stores/offline.js (уже написан, активировать)
       web/vite.config.js (настроить Service Worker)
Тест: Playwright offline mode tests
```

---

## Быстрые команды

```bash
# Запуск тестов
cd /home/hive/BEEBOT && pytest tests/ -v

# Запуск конкретного теста
pytest tests/test_integram_v2_client.py -v

# Lint
ruff check src/

# Статус VPS
ssh ai-agent@185.233.200.13 "docker logs --tail 30 beebot"

# Быстрый тест подключения CRM на VPS
ssh ai-agent@185.233.200.13 "docker exec beebot python -c \"from src.crm_factory import get_crm_client; import asyncio; c=get_crm_client(); asyncio.run(c.authenticate()); print('CRM OK')\""

# Switch для push в upstream
gh auth switch -u unidel2035 && gh auth setup-git
# После деплоя вернуть
gh auth switch -u gaveron18
```

---

## Структура коммит-сообщений

```
fix(crm-v2): краткое описание баг-фикса
feat(diary): добавить FSM команды /diary
refactor(analytics): перенести логику из агента в AnalyticsService
test(memory): добавить тест agent_id namespace
docs(architecture): обновить диаграмму Service Layer
chore(ci): добавить проверку типов mypy
```

---

## Что делать при проблемах

```
Тесты падают:
  → Читать traceback полностью
  → pytest -x --tb=short для первой ошибки
  → НЕ менять тест чтобы он прошёл — исправить код

Бот не запускается на VPS:
  → docker logs beebot 2>&1 | tail -50
  → Первая гипотеза: я сломал. Проверить последний коммит.
  → docker compose down && docker compose up -d --build

CRM недоступна:
  → Проверить туннель: systemctl status groq-tunnel groq-proxy
  → Graceful degradation в коде должна это обрабатывать

PR не принимается CI:
  → Смотреть Actions на GitHub
  → ruff check src/ && mypy src/ && bandit -r src/ локально
```

---

*Файл: docs/execution_prompt.md*
*Обновлять при изменении workflow или добавлении новых паттернов*
