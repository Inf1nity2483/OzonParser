# Лог работы с ИИ (Cursor)

## Сессия 1: Планирование архитектуры

**Промпт:**
> Давай разбирать — [полное ТЗ на пайплайн аналитики маркетплейсов]

**Решения ИИ:**
- Выбран Ozon как маркетплейс (по запросу пользователя)
- **Ключевое решение:** Ozon Seller API не подходит для мониторинга конкурентов — используем публичный `composer-api.bx`
- OpenAI gpt-4o-mini + AmoCRM
- Батчинг LLM: 50 товаров на запрос вместо 10 000 отдельных вызовов
- SQLite-кэш для повторных классификаций
- Checkpoint после каждой страницы для graceful degradation

**Уточнения от пользователя:**
- Маркетплейс: Ozon
- Уровень: полная реализация (код) / демо с моками при antibot и нулевой квоте OpenAI
- LLM + CRM: OpenAI + AmoCRM

---

## Сессия 2: Реализация

**Промпт:**
> Implement the plan as specified

**Что сгенерировал ИИ:**
1. Структура проекта по ТЗ
2. `OzonClient` с tenacity retry и обработкой 429
3. `OzonParser` с парсингом widgetStates и checkpoint
4. `Normalizer` → Pydantic `Product`
5. `SegmentClassifier` с OpenAI structured outputs и mock-режимом
6. `AmoCRMClient` с OAuth refresh и mock JSON fallback
7. `TaskSelector` — интересные позиции (affordable premium, high-rated standard)
8. `PipelineOrchestrator` + CLI
9. Docker, CI/CD, unit-тесты

**Что исправляли вручную / после тестов:**
- Парсинг цены `priceV2.price[{text: "12990"}]` — рекурсивный обход list/dict
- Ozon antibot (403) — `PARSER_MOCK` и fallback на синтетику, если сбор = 0
- UnicodeEncodeError на Windows — `sys.stdout.reconfigure(encoding="utf-8")`
- Замена `pytest-httpx` на `unittest.mock`
- Dockerfile: копировать `README.md` (hatchling требует readme из pyproject)

---

## Сессия 3: Прогон, 429 на всех HTTP-слоях, документация

**Промпты:**
> Проверь решение и прогони, в .env уже все ключи  
> Добавь проверку 429 на слоях с http  

**Что сделано:**
- Вынесен общий модуль `src/http/rate_limit.py` (Retry-After + `RateLimitError`)
- Подключён в Ozon, AmoCRM, OpenAI-классификатор (tenacity 1→2→4→8 с)
- AmoCRM: подтверждён живой `POST /api/v4/tasks` (200)
- OpenAI: `insufficient_quota` → retry → mock fallback (ожидаемо без баланса)
- README / `.env.example` / `AI_USAGE` приведены к фактическим ограничениям (antibot, моки)

---

## Примеры полезных промптов

### Генерация тестов
```
Напиши pytest-тесты для OzonParser.parse_widget_states с fixture JSON
из реального ответа composer-api. Покрой edge cases: пустой ответ,
битый JSON в widget, дедупликация по id.
```

### Отладка парсера
```
Помоги разобраться с Ozon composer-api, вот ошибка: widgetStates
возвращает priceV2 в формате {"price": [{"text": "12990"}]}.
Как правильно извлечь числовую цену?
```

### AmoCRM OAuth
```
Напиши async Python клиент для AmoCRM API v4: создание задач через
POST /api/v4/tasks с auto-refresh токена по 401.
```

### HTTP 429
```
Добавь единую обработку HTTP 429 для Ozon, AmoCRM и OpenAI:
Retry-After если есть, иначе exponential backoff, tenacity retry.
```

---

## Архитектурные решения (для защиты)

| Решение | Почему |
|---------|--------|
| composer-api вместо Seller API | Seller API — только свои товары; задание про мониторинг категории |
| Multi-item LLM batching | 10k запросов = дорого и долго; ~200 запросов по 50 товаров |
| SQLite cache | Повторные прогоны без затрат на API |
| Checkpoint per page | Graceful degradation: прогресс при 429/сбое |
| `PARSER_MOCK` / fallback | Ozon antibot 403 на non-browser клиентах |
| `CRM_MOCK` / `LLM_MOCK` | CI и локальная разработка без ключей/квоты |
| Общий `src/http/rate_limit` | Одинаковый контракт 429 на всех HTTP-слоях |
| TaskSelector с квартилями | «Интересные» = нишевая премиум + топ standard по рейтингу |

---

## Стоимость полного прогона (оценка)

- Ozon: бесплатно (публичный API; доступ не гарантирован из‑за antibot)
- OpenAI gpt-4o-mini: ~200 запросов × ~2k tokens ≈ $2–5
- AmoCRM: бесплатный тестовый аккаунт
