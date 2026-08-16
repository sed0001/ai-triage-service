"""Демо-клиент: отправляет набор примеров обращений в POST /triage.

Запуск (сервис должен быть поднят на 127.0.0.1:8000):
    python scripts/demo_client.py
    python scripts/demo_client.py --host http://localhost:8001
"""

import argparse
import sys

import requests

# Русские сообщения должны корректно печататься в любой консоли
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

BASE_URL = "http://127.0.0.1:8000"

# Примеры обращений: (channel, client_id, text)
SAMPLES = [
    ("email", "client-001", "Здравствуйте! Мне дважды списали деньги за подписку, верните один платёж."),
    ("chat", "client-002", "Подскажите, как сменить тариф на более дешёвый?"),
    ("form", "client-003", "После оплаты не открывается личный кабинет, что делать?"),
    ("email", "client-004", "Это безобразие! Сервис вообще не работает, верните деньги!"),
    ("chat", "client-005", "Подскажите, во сколько закрывается пункт выдачи?"),
]


def run(host: str) -> None:
    """Отправляет все примеры обращений и печатает ответы."""
    url = f"{host}/triage"
    for channel, client_id, text in SAMPLES:
        payload = {"text": text, "channel": channel, "client_id": client_id}
        print(f">>> {channel} / {client_id}\n    {text[:80]}")
        try:
            resp = requests.post(url, json=payload, timeout=120)
            print(f"    HTTP {resp.status_code}: {resp.json()}")
        except requests.RequestException as exc:
            print(f"    Ошибка запроса: {exc}", file=sys.stderr)
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Отправляет примеры обращений в /triage")
    parser.add_argument("--host", default=BASE_URL, help=f"Адрес сервиса (по умолчанию {BASE_URL})")
    args = parser.parse_args()
    run(args.host)