"""Логика обработки обращения: лимит → LLM/база знаний → запись в БД.

Здесь же собраны бизнес-правила (приведение категорий к нормальному виду,
принудительная эскалация при низкой уверенности, фолбэк при сбое LLM).
Если LLM_API_KEY не задан, работаем в демо-режиме базы знаний: готовые
ответы подбираются из examples/knowledge_base.json вместо вызова модели.
"""

import sqlite3

from app.config import settings
from app.core.llm import FALLBACK_REPLY, LLMError
from app.core.state import get_knowledge_base, get_llm, get_rate_limiter
from app.db import database
from app.logging_setup import get_logger
from app.schemas import TriageRequest, TriageResponse

logger = get_logger(__name__)

VALID_CATEGORIES = ("billing", "support", "complaint", "other")
VALID_CONFIDENCE = ("high", "medium", "low")


class RateLimitError(Exception):
    """Превышен лимит запросов в минуту для client_id."""


class StorageError(Exception):
    """Не удалось сохранить запись в базу данных."""


def _fallback_response() -> TriageResponse:
    """Шаблонный ответ «если всё сломалось»: эскалация, низкая уверенность."""
    return TriageResponse(
        category="other",
        confidence="low",
        draft_reply=FALLBACK_REPLY,
        escalate=True,
    )


def _build_response(data: dict) -> TriageResponse:
    """Нормализует ответ модели до контракта TriageResponse.

    Невалидные значения полей трактуются как сбой модели (LLMError),
    чтобы сервис вернул шаблонный ответ с эскалацией.
    """
    category = str(data.get("category", "")).strip().lower()
    confidence = str(data.get("confidence", "")).strip().lower()

    if category not in VALID_CATEGORIES:
        raise LLMError(f"Модель вернула недопустимую категорию: {category or 'пусто'}")
    if confidence not in VALID_CONFIDENCE:
        raise LLMError(f"Модель вернула недопустимую уверенность: {confidence or 'пусто'}")

    draft_reply = str(data.get("draft_reply", "")).strip()
    if not draft_reply:
        raise LLMError("Модель вернула пустой черновик ответа")

    # Бизнес-правило: при низкой уверенности обращение уходит человеку
    escalate = bool(data.get("escalate", False)) or confidence == "low"

    return TriageResponse(
        category=category,
        draft_reply=draft_reply,
        confidence=confidence,
        escalate=escalate,
    )


def _triage_via_knowledge_base(text: str) -> tuple[TriageResponse, str | None]:
    """Подбор готового ответа из базы знаний (демо-режим без ключа LLM).

    Точное совпадение или совпадение по ключевым словам вернёт запись из JSON;
    иначе — общий шаблон с эскалацией (как при сбое LLM).
    """
    entry = get_knowledge_base().lookup(text)
    if entry is None:
        logger.error("База знаний: совпадение для обращения не найдено, отдан шаблон")
        return _fallback_response(), "knowledge_base_no_match"
    try:
        return _build_response(entry), None
    except LLMError as exc:
        logger.error("База знаний: невалидная запись: %s", exc)
        return _fallback_response(), str(exc)


def process_triage(payload: TriageRequest) -> TriageResponse:
    """Полный цикл обработки обращения с записью в журнал аудита."""
    client_id = payload.client_id

    # Шаг 1. Лимитирование по client_id (скользящее окно)
    if not get_rate_limiter().check(client_id):
        database.insert_ticket(
            client_id=client_id,
            channel=payload.channel,
            text=payload.text,
            error="rate_limit_exceeded",
        )
        logger.warning("Превышен лимит запросов: client_id=%s", client_id)
        raise RateLimitError("rate limit exceeded")

    # Шаг 2a. Демо-режим: без ключа LLM используется база знаний
    if not settings.llm_api_key.strip():
        result, error = _triage_via_knowledge_base(payload.text)
    # Шаг 2b. Основной режим: LLM с фолбэком «если всё сломалось»
    else:
        error = None
        try:
            data = get_llm().classify(payload.text)
            result = _build_response(data)
        except LLMError as exc:
            error = str(exc)
            logger.error("Сбой LLM для client_id=%s: %s", client_id, exc)
            result = _fallback_response()

    # Шаг 3. Сохранение результата (аудит)
    try:
        database.insert_ticket(
            client_id=client_id,
            channel=payload.channel,
            text=payload.text,
            category=result.category,
            confidence=result.confidence,
            escalate=result.escalate,
            draft_reply=result.draft_reply,
            error=error,
        )
    except sqlite3.Error as exc:
        logger.error("Не удалось сохранить тикет в БД: %s", exc)
        raise StorageError("Не удалось сохранить результат в базу данных") from exc

    logger.info(
        "Триаж завершён: client_id=%s channel=%s category=%s confidence=%s escalate=%s",
        client_id,
        payload.channel,
        result.category,
        result.confidence,
        result.escalate,
    )
    return result