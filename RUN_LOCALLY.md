# Локальный запуск пошагово

Проверено на Windows 10/11 + PowerShell. Команды для macOS/Linux — в комментариях.
Время: ~10 минут.

## Шаг 0. Что нужно

- Python 3.10+ (`python --version`)
- (Для проверки БД) SQLite-клиент: `sqlite3 file.db "..."` — встроен в macOS/Linux;
  в Windows можно использовать утилиты вроде DB Browser for SQLite или PowerShell (см. Шаг 7).

## Шаг 1. Скопировать `.env` и вписать ключ

```powershell
Copy-Item .env.example .env
# macOS/Linux: cp .env.example .env
```

Открыть `.env` и вписать API-ключ ProxyAPI:

```
LLM_API_KEY=sk-...
```

Ключ создаётся в личном кабинете ProxyAPI: https://console.proxyapi.ru/keys
(пункт «API ключи» → «Создать ключ» → скопировать значение).

> `.env` — секрет, в git не попадёт (он в `.gitignore`). Без ключа сервис работает
> в демо-режиме базы знаний: тексты из `examples/test_data.md` вернут свои ответы
> из `examples/knowledge_base.json`, а прочие — честный шаблон «передано оператору»
> с `escalate: true`.

## Шаг 2. Виртуальное окружение

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# macOS/Linux: python3 -m venv .venv && source .venv/bin/activate
```

В активированном окружении в строке терминала появится `(.venv)`.

## Шаг 3. Зависимости

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt   # для тестов и смоук-проверки
```

## Шаг 4. Запустить сервис

Обязательно из корня проекта (папки `ai-triage-service`):

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

В логе появится адрес, например `http://0.0.0.0:8000`. Папки `logs/` и `data/`
создадутся автоматически при первом запуске.

## Шаг 5. Проверить, что сервис жив

- Открыть в браузере `http://127.0.0.1:8000/health` → ответ `{"status": "ok", ...}`.
- Открыть `http://127.0.0.1:8000/docs` — интерактивная документация (Swagger),
  можно отправлять запросы прямо из браузера.

## Шаг 6. Отправить обращение

Пример через curl:

```powershell
curl.exe -X POST http://127.0.0.1:8000/triage ^
  -H "Content-Type: application/json" ^
  -d '{\"text\": \"Мне дважды списали деньги за подписку.\", \"channel\": \"email\", \"client_id\": \"client-001\"}'
```

Или через Postman / `docs`: тело запроса —

```json
{
  "text": "Мне дважды списали деньги за подписку.",
  "channel": "email",
  "client_id": "client-001"
}
```

Ещё 5 готовых обращений с ожидаемыми категориями — в `examples/test_data.md`.
Поле `channel` принимает только `email`, `form`, `chat`; другое значение вернёт 422.

## Шаг 7. Проверить БД и логи

Остановить сервис (Ctrl+C) и посмотреть данные. В Windows проще всего через
однострочник на Python (внешние утилиты не нужны):

```powershell
python -c "import sqlite3; [print(tuple(r)) for r in sqlite3.connect(r'data\tickets.db').execute('SELECT id, client_id, channel, category, confidence, escalate, error FROM tickets ORDER BY id DESC LIMIT 10;')]"
# список каналов из справочника:
python -c "import sqlite3; [print(tuple(r)) for r in sqlite3.connect(r'data\tickets.db').execute('SELECT * FROM channels;')]"
```

```bash
# macOS / Linux / Git Bash: sqlite3
sqlite3 data/tickets.db "SELECT id, client_id, channel, category, confidence, escalate, error FROM tickets ORDER BY id DESC LIMIT 10;"
sqlite3 data/tickets.db "SELECT * FROM channels;"
```

Логи — в `logs/`: `app.log` (события), `error.log` (ошибки), `requests.log` (аудит запросов).

## Шаг 8. Проверить лимит 5 запросов/минуту

Отправить подряд **6** одинаковых запросов с одним `client_id`. Шестой вернёт
`429 Too Many Requests` — это работа лимитера.

## Шаг 9. (Опционально) полная проверка проекта

```powershell
python scripts/run_checks.py
```

Прогонит все юнит-тесты и смоук-тест; в конце — итог «OK / сервис работает».

## Устранение неполадок

| Симптом | Причина / решение |
|---|---|
| `ModuleNotFoundError` | Не активировано venv (Шаг 2) или не установлены зависимости (Шаг 3) |
| `401`/`invalid api key` в логах | Неверный `LLM_API_KEY` в `.env` (Шаг 1) |
| Ответ — шаблон «передано оператору» (`escalate: true`) | Текст в демо-режиме не совпал с базой знаний, либо задан `LLM_API_KEY`, но модель недоступна; причина в `logs/error.log` |
| Кракозябры в консоли Windows | Включить UTF-8: `chcp 65001` либо перезапустить терминал перед Шагом 4 |
| `422`, поле `channel` | Использовать одно из значений: `email`, `form`, `chat` |