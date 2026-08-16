"""Юнит-тесты модуля БД: создание файла при первом запуске, запись, healthcheck."""

from pathlib import Path

import pytest

from app.config import settings
from app.db import database


def _use_tmp_db(tmp_path, monkeypatch) -> Path:
    """Переводит модуль БД на временный файл и сбрасывает флаг инициализации."""
    db_file = tmp_path / "tickets_test.db"
    monkeypatch.setattr(settings, "db_path", str(db_file))
    monkeypatch.setattr(database, "_initialized", False)
    return db_file


def test_init_db_creates_file_on_first_run(tmp_path, monkeypatch):
    """Первый запуск создаёт файл БД."""
    db_file = _use_tmp_db(tmp_path, monkeypatch)
    assert not db_file.exists()
    database.init_db()
    assert db_file.exists()


def test_init_db_reuses_existing_file(tmp_path, monkeypatch):
    """Повторный запуск использует уже существующий файл."""
    db_file = _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    # кладём одну запись «от прошлого запуска»
    database.insert_ticket(client_id="old", channel="chat", text="данные из прошлого запуска")
    first_id = database.insert_ticket(client_id="old", channel="chat", text="вторая запись")

    # повторная инициализация не должна ничего потерять
    database.init_db()
    with database._connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    assert count == 2


def test_insert_and_healthcheck(tmp_path, monkeypatch):
    db_file = _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    ticket_id = database.insert_ticket(
        client_id="c1",
        channel="email",
        text="верните деньги",
        category="billing",
        confidence="high",
        escalate=False,
        draft_reply="Проверим платёж.",
    )
    assert ticket_id > 0
    assert database.db_healthcheck() is True


def test_insert_rejected_request(tmp_path, monkeypatch):
    """Отклонённый запрос сохраняется с error и без результата."""
    db_file = _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    database.insert_ticket(client_id="c2", channel="chat", text="тест", error="rate_limit_exceeded")
    with database._connect() as conn:
        row = conn.execute("SELECT error, category FROM tickets WHERE client_id='c2'").fetchone()
    assert row["error"] == "rate_limit_exceeded"
    assert row["category"] is None


def test_channels_reference_seeded(tmp_path, monkeypatch):
    """Справочник каналов заполняется при первом запуске (вариант B)."""
    _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    with database._connect() as conn:
        rows = conn.execute("SELECT name FROM channels ORDER BY name").fetchall()
    assert [row["name"] for row in rows] == ["chat", "email", "form"]


def test_invalid_channel_rejected_by_db(tmp_path, monkeypatch):
    """Несуществующий канал отклоняется внешним ключом на уровне БД."""
    _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        database.insert_ticket(client_id="c3", channel="phone", text="тест")


def test_invalid_category_rejected_by_db(tmp_path, monkeypatch):
    """Недопустимая категория отклоняется CHECK-ограничением на уровне БД."""
    _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        database.insert_ticket(
            client_id="c4",
            channel="email",
            text="тест",
            category="refund",
            confidence="high",
            escalate=False,
            draft_reply="ok",
        )


def test_database_path_used_from_settings(tmp_path, monkeypatch):
    """Проверяем, что файл БД создаётся ровно в settings.db_path."""
    db_file = _use_tmp_db(tmp_path, monkeypatch)
    database.init_db()
    assert db_file.name == "tickets_test.db"