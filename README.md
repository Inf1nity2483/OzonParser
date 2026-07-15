# Пайплайн аналитики маркетплейсов (Ozon → LLM → AmoCRM)

Сбор каталога Ozon (категория «Смартфоны») → нормализация в Pydantic → классификация ценового сегмента (OpenAI) → задачи менеджерам в AmoCRM.

**Стек:** Ozon · OpenAI (`gpt-4o-mini`) · AmoCRM · Python 3.12+

**Уровень сдачи:** автоматизация и инфраструктура уровня Full; живой storefront Ozon часто режется antibot (403) — для локального/CI демо используется `PARSER_MOCK`. Реальный клиент AmoCRM и код OpenAI (батчинг + кэш) есть; без квоты OpenAI включайте `LLM_MOCK=true`.

## Архитектура

```
Ozon (composer-api) → Parser → Normalizer → LLM Classifier → Task Selector → AmoCRM
         │                 ↓                      ↓
         │            Checkpoint             SQLite Cache
         └─ 429: Retry-After + exponential backoff (общий слой src/http/)
```

## Быстрый старт (рекомендуемый демо-режим)

```bash
cp .env.example .env
pip install -e ".[dev]"
python -m src.main run
```

`.env.example` уже настроен на безопасное демо без внешних квот:

| Флаг | Значение | Зачем |
|------|----------|--------|
| `DEMO_MODE` | `true` | 100 товаров вместо 10 000 |
| `PARSER_MOCK` | `true` | синтетический каталог (Ozon antibot) |
| `LLM_MOCK` | `true` | классификация по правилам без OpenAI |
| `CRM_MOCK` | `true` | задачи в `data/tasks.json` |

**Windows (PowerShell), если нужно переопределить флаги:**

```powershell
$env:DEMO_MODE="true"; $env:PARSER_MOCK="true"; $env:LLM_MOCK="true"; $env:CRM_MOCK="true"
python -m src.main run
```

### Docker

```bash
docker compose up --build
```

`docker-compose.yml` по умолчанию поднимает пайплайн с mock-флагами (`DEMO_MODE` / `PARSER_MOCK` / `LLM_MOCK` / `CRM_MOCK`).  
Если в `.env` выставить, например, `LLM_MOCK=false`, compose подхватит это значение — без баланса OpenAI прогон будет долго ретраить 429.

Результаты пишутся в `./data/` (том смонтирован в контейнер).

## Результаты прогона

| Файл | Содержание |
|------|------------|
| `data/raw_products.json` | сырой сбор |
| `data/products.json` | нормализованные `Product` |
| `data/enriched_products.json` | товары с полем `segment` |
| `data/tasks.json` | задачи CRM (в `CRM_MOCK=true`) |
| `data/report.json` | отчёт: собрано / ошибки / сегменты / CRM |
| `data/demo_run.txt` | лог успешного демо для проверяющих |

Пример отчёта:

```
============================================================
ОТЧЁТ О ВЫПОЛНЕНИИ ПАЙПЛАЙНА
============================================================
Собрано: 100 | Нормализовано: 100 | Ошибки парсинга: 0
LLM: 100 классифицировано | cache hit: 0 | API calls: 0
Сегменты: Стандарт: 35 | Премиум: 23 | Эконом: 42
CRM: 10 задач создано | ошибок: 0
============================================================
```

## Переменные окружения

| Переменная | Описание | По умолчанию в коде |
|------------|----------|---------------------|
| `DEMO_MODE` | 50–100 товаров вместо 10 000 | `false` |
| `DEMO_TARGET_COUNT` | размер демо | `100` |
| `TARGET_PRODUCT_COUNT` | цель полного прогона | `10000` |
| `PARSER_MOCK` | синтетика вместо Ozon API | `false` |
| `LLM_MOCK` | rule-based сегменты без OpenAI | `false` |
| `CRM_MOCK` | задачи в JSON вместо AmoCRM API | `false` |
| `LLM_BATCH_SIZE` | товаров в одном запросе к LLM | `50` |
| `OPENAI_API_KEY` | ключ OpenAI | — |
| `AMOCRM_SUBDOMAIN` | поддомен `*.amocrm.ru` | — |
| `AMOCRM_ACCESS_TOKEN` / `REFRESH_TOKEN` | OAuth токены | — |

Полный список — [`.env.example`](.env.example). Файл `.env` в git не коммитить.

## Режимы запуска

### Только локальная проверка / CI

Используйте значения из `.env.example` (все mock + `DEMO_MODE`).

### Реальный AmoCRM + mock парсер/LLM

```bash
# .env
DEMO_MODE=true
PARSER_MOCK=true
LLM_MOCK=true
CRM_MOCK=false
# + заполненные AMOCRM_*
python -m src.main run
```

### Полный прогон (10 000)

Нужны: доступ к Ozon без 403, баланс OpenAI, валидные токены AmoCRM (`access` + желательно `refresh`).

```bash
DEMO_MODE=false
PARSER_MOCK=false
LLM_MOCK=false
CRM_MOCK=false
python -m src.main run
```

После сбоя можно продолжить с checkpoint:

```bash
python -m src.main run --resume
```

## Ограничения (важно для ревью)

1. **Ozon antibot** — публичный `composer-api.bx` часто отвечает `403` на non-browser клиенты. Реализованы пагинация, 429-retry, checkpoint и разбор `widgetStates` (см. `tests/fixtures/ozon_page.json`). Для стабильного демо — `PARSER_MOCK=true`; при полном отказе API парсер логирует ошибку и может отдать синтетику, чтобы пайплайн не падал.
2. **OpenAI** — при `insufficient_quota` / 429 классификатор делает retry, затем fallback на rule-based сегменты. Для сдачи без биллинга держите `LLM_MOCK=true`.
3. **AmoCRM** — создание задач через API v4 проверено. Без `AMOCRM_REFRESH_TOKEN` обновление по 401 недоступно: нужен свежий `access_token` или mock.

## Получение ключей

### Ozon
Отдельный seller-аккаунт не нужен (используется storefront composer-api). Seller API не подходит: отдаёт только свои товары, а задание — мониторинг категории.

### OpenAI
1. [platform.openai.com](https://platform.openai.com) → API key  
2. `OPENAI_API_KEY` в `.env`, `LLM_MOCK=false`

### AmoCRM
1. Тестовый аккаунт на [amocrm.ru](https://www.amocrm.ru)  
2. Настройки → Интеграции → своя интеграция  
3. OAuth: `client_id`, `client_secret`, `access_token`, `refresh_token`  
4. `CRM_MOCK=false`

## Разработка

```bash
pip install -e ".[dev]"
pytest --cov=src --cov-fail-under=70 -v
ruff check src tests
```

CI (GitHub Actions): lint + pytest с mock-флагами, порог покрытия 70% — [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

### Структура

```
src/
├── parser/       # Ozon: HTTP-клиент, пагинация, checkpoint, mock-данные
├── normalizer/   # Raw → Pydantic Product
├── llm/          # batch classification, prompts, SQLite cache
├── crm/          # AmoCRM client, выбор «интересных» товаров
├── http/         # общая обработка HTTP 429
├── pipeline/     # orchestrator + reporter
├── storage/      # checkpoint store
├── models/       # Product, CRMTask, PipelineReport
└── main.py       # CLI: python -m src.main run [--resume]
tests/            # unit + e2e на моках
docs/task.txt     # исходное ТЗ
AI_USAGE.md       # лог работы с ИИ (требуется заданием)
```

Лог промптов и архитектурных решений: [AI_USAGE.md](AI_USAGE.md).
