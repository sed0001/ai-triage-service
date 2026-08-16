"""Настройка логирования: консоль + файлы logs/app.log, logs/error.log, logs/requests.log.

Ошибки дублируются в отдельный error.log, а каждое HTTP-обращение пишется
в requests.log отдельным логгером. Папка logs/ создаётся автоматически.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _add_file_handler(logger_: logging.Logger, filename: str, level: int) -> None:
    """Добавляет логгеру ротируемый файловый хендлер в папке logs/."""
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / filename,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    logger_.addHandler(handler)


def setup_logging() -> None:
    """Инициализирует хендлеры (вызывается один раз)."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Консольный вывод для локального запуска
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    root.addHandler(console)

    # app.log — все события сервиса
    _add_file_handler(root, "app.log", logging.DEBUG)

    # error.log — только ошибки (ошибки пишутся и в app.log через корневой логгер)
    _add_file_handler(root, "error.log", logging.ERROR)

    # requests.log — аудит HTTP-запросов (отдельный логгер)
    req_logger = logging.getLogger("requests")
    req_logger.setLevel(logging.INFO)
    req_logger.propagate = False
    _add_file_handler(req_logger, "requests.log", logging.INFO)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Возвращает логгер, при необходимости предварительно настроив его."""
    setup_logging()
    return logging.getLogger(name)