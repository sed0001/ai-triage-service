"""Работа с SQLite: инициализация схемы, запись тикетов, healthcheck.

Таблица tickets хранит входные данные обращения, результат обработки
и текст ошибки (если обработка не удалась) — журнал для аудита.
"""

import datetime as dt
import sqlite3
from pathlib import Path

from app.config import settings
from app.logging_setup import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    client_id TEXT NOT NULL,
    channel TEXT NOT NULL REFERENCES channels(name),
    text TEXT NOT NULL,
    category TEXT CHECK (category IN ('billing', 'support', 'complaint', 'other')),
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    escalate INTEGER CHECK (escalate IN (0, 1)),
    draft_reply TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets (created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_client_id ON tickets (client_id);
"""

# Справочник каналов обращений: источник, из которого поступило сообщение.
# Реальные интеграции (почта/форма/чат) пока не подключаются — канал передаётся
# как метка в запросе, но на уровне БД значения жёстко ограничены справочником.
_CHANNELS = (
    ("email", "электронная почта"),
    ("form", "форма на сайте"),
    ("chat", "чат поддержки"),
)

# Флаг ленивой инициализации схемы: чтобы таблицы создавались и в тестах
_initialized = False


def _seed_channels(conn: sqlite3.Connection) -> None:
    """Заполняет справочник channels допустимыми каналами (идемпотентно)."""
    conn.executemany("INSERT OR IGNORE INTO channels (name, description) VALUES (?, ?)", _CHANNELS)


def _ensure_schema() -> None:
    """Создаёт таблицы и индексы при первом обращении к БД (идемпотентно).

    Схема включает целостность на уровне БД: справочник каналов с внешним ключом,
    NOT NULL на обязательные поля и CHECK-ограничения значений категории,
    уверенности и флага эскалации.
    """
    global _initialized
    if _initialized:
        return
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.db_path) as conn:
        # executescript: в _SCHEMA несколько операторов (таблицы + индексы)
        conn.executescript(_SCHEMA)
        _seed_channels(conn)
        conn.commit()
    _initialized = True


def _connect() -> sqlite3.Connection:
    """Открывает соединение с БД, при первом обращении создавая схему."""
    _ensure_schema()
    conn = sqlite3.connect(settings.db_path)
    # Включаем контроль внешних ключей (channel -> channels.name)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Инициализирует базу данных при старте приложения.

    Если файл БД уже существует — он используется как есть (данные
    сохраняются между запусками). Если файла нет — создаётся новый.
    Схема таблицы создаётся идемпотентно (CREATE TABLE IF NOT EXISTS).
    """
    existed = Path(settings.db_path).exists()
    _ensure_schema()
    if existed:
        logger.info("База данных найдена и используется: %s", settings.db_path)
    else:
        logger.info("База данных создана: %s", settings.db_path)


def insert_ticket(
    client_id: str,
    channel: str,
    text: str,
    category: str | None = None,
    confidence: str | None = None,
    escalate: bool | None = None,
    draft_reply: str | None = None,
    error: str | None = None,
) -> int:
    """Сохраняет обработку обращения и возвращает id новой записи.

    Названия параметров совпадают с колонками таблицы. Для отклонённых
    запросов (превышение лимита) сохраняются только вход + error.
    """
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    escalate_int = (1 if escalate else 0) if escalate is not None else None
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tickets
                (created_at, client_id, channel, text, category, confidence, escalate, draft_reply, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, client_id, channel, text, category, confidence, escalate_int, draft_reply, error),
        )
        conn.commit()
        ticket_id = int(cursor.lastrowid)
    logger.debug("Тикет сохранён: id=%s client_id=%s", ticket_id, client_id)
    return ticket_id


def db_healthcheck() -> bool:
    """Проверяет доступность БД простым запросом."""
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        logger.error("База данных недоступна", exc_info=True)
        return False