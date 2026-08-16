"""Запуск всех проверок проекта: юнит-тесты (pytest) + смоук-тест сервиса.

Запуск (из корня проекта):
    python scripts/run_checks.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Русские сообщения должны корректно печататься в любой консоли
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def main() -> int:
    print("=== 1/2 Юнит-тесты (pytest) ===")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    if result.returncode != 0:
        print("Юнит-тесты не прошли")
        return result.returncode

    print("\n=== 2/2 Смоук-тест сервиса ===")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_test.py")], cwd=ROOT)
    if result.returncode != 0:
        print("Смоук-тест не прошёл")
        return result.returncode

    print("\nВсе проверки пройдены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())