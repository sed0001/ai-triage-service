"""Смоук-тест сервиса: автоматически поднимает приложение и проверяет ответы.

Проверяет:
  - GET  /health               -> 200
  - POST /triage (валидный)    -> 200 (демо-режим базы знаний без ключа LLM)
  - POST /triage (422)         -> пустой / слишком длинный text, неверный channel
  - POST /triage (429)         -> шестой запрос на тот же client_id
  - база знаний                -> текст из examples/test_data.md возвращает запись из JSON
  - запись в БД (tickets)      -> есть строки, в том числе зафиксированен лимит
  - файлы логов                -> app.log, error.log, requests.log

Сервер запускается на локальном порту с временной БД и логами,
поэтому рабочие данные проекта не затрагиваются. Сеть не нужна.

Запуск (из корня проекта):
    python scripts/smoke_test.py
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8010
BASE_URL = f"http://127.0.0.1:{PORT}"

# Русские сообщения и пути должны корректно печататься в любой консоли
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PASSED = 0
FAILED = 0


def report(ok: bool, label: str, detail: str = "") -> None:
    """Печатает результат проверки и накапливает счётчики."""
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [OK] {label}")
    else:
        FAILED += 1
        print(f"  [FAIL] {label} {detail}")


def http_post(path: str, payload: dict) -> tuple[int, dict]:
    """Отправляет POST и возвращает (status_code, json)."""
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Connection": "close"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def http_get(path: str) -> tuple[int, dict]:
    """Отправляет GET и возвращает (status_code, json)."""
    request = urllib.request.Request(BASE_URL + path, headers={"Connection": "close"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def wait_until_healthy(timeout: float = 30.0) -> bool:
    """Ждёт, пока сервер начнёт отвечать на /health."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _ = http_get("/health")
            if status == 200:
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def main() -> int:
    global PASSED, FAILED
    tmp_dir = Path(tempfile.mkdtemp(prefix="triage_smoke_"))
    print(f"Временные данные: {tmp_dir}")

    env = dict(os.environ)
    env["DB_PATH"] = str(tmp_dir / "tickets_smoke.db")
    env["LOG_DIR"] = str(tmp_dir / "logs")

    # Вывод сервера пишем в файл, чтобы не блокировать процесс на заполненном пайпе
    server_stdout = open(tmp_dir / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT,
        env=env,
        stdout=server_stdout,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        report(wait_until_healthy(), "сервер запущен, /health отвечает 200")

        # Валидный запрос без совпадения в базе знаний -> шаблон с эскалацией
        status, body = http_post("/triage", {"text": "Просто проверка смоука.", "channel": "email", "client_id": "smoke-0001"})
        report(
            status == 200 and body.get("escalate") is True and body.get("confidence") == "low",
            "валидный запрос возвращает 200 (шаблон с эскалацией без совпадения)",
            f"-> {status} {body}",
        )

        # База знаний: текст из examples/test_data.md воспроизводится один в один
        kb_text = "Здравствуйте! Мне дважды списали деньги за подписку, верните, пожалуйста, один платёж."
        status, body = http_post("/triage", {"text": kb_text, "channel": "email", "client_id": "smoke-kb"})
        report(
            status == 200
            and body.get("category") == "billing"
            and body.get("confidence") == "medium"
            and body.get("escalate") is False
            and bool(body.get("draft_reply")),
            "база знаний: точное совпадение возвращает запись из JSON",
            f"-> {status} {body}",
        )

        # Ошибки валидации -> 422
        status, _ = http_post("/triage", {"text": "   ", "channel": "email", "client_id": "smoke-0002"})
        report(status == 422, "пустой text отклоняется (422)", f"-> {status}")

        status, _ = http_post("/triage", {"text": "x" * 2001, "channel": "email", "client_id": "smoke-0002"})
        report(status == 422, "text длиннее 2000 символов отклоняется (422)", f"-> {status}")

        status, _ = http_post("/triage", {"text": "привет", "channel": "phone", "client_id": "smoke-0002"})
        report(status == 422, "неизвестный channel отклоняется (422)", f"-> {status}")

        status, _ = http_post("/triage", {"text": "привет", "channel": "email"})
        report(status == 422, "отсутствует client_id отклоняется (422)", f"-> {status}")

        # Лимит 5 запросов/мин -> шестой 429
        codes = []
        for i in range(6):
            status, _ = http_post("/triage", {"text": f"тест {i}", "channel": "chat", "client_id": "smoke-rl"})
            codes.append(status)
        report(
            codes[:5] == [200] * 5 and codes[5] == 429,
            "лимит 5 запросов/мин: 6-й запрос отклоняется (429)",
            f"-> коды {codes}",
        )

        # Проверка БД: фолбэки и отклонённые запросы записаны
        conn = sqlite3.connect(str(tmp_dir / "tickets_smoke.db"))
        total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        fallbacks = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE client_id='smoke-0001' AND error IS NOT NULL"
        ).fetchone()[0]
        rate_limited = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE error='rate_limit_exceeded'"
        ).fetchone()[0]
        conn.close()
        report(total >= 6, "в БД сохранены записи обращений", f"-> всего {total}")
        report(fallbacks == 1, "шаблон без совпадения записан вместе с error", f"-> шаблонов {fallbacks}")
        report(rate_limited == 1, "превышение лимита зафиксировано в БД", f"-> записей {rate_limited}")

        # Проверка логов
        log_dir = tmp_dir / "logs"
        expected_logs = ["app.log", "error.log", "requests.log"]
        for name in expected_logs:
            file = log_dir / name
            report(file.exists() and file.stat().st_size > 0, f"создан лог {name}", f"-> {file.stat().st_size if file.exists() else 0} байт")

        error_log = (log_dir / "error.log").read_text(encoding="utf-8") if (log_dir / "error.log").exists() else ""
        report("База знаний" in error_log, "в error.log есть запись о шаблоне без совпадения")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        server_stdout.close()

    print(f"\nИтог: {PASSED} пройдено, {FAILED} ошибок")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())