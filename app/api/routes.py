"""HTTP-эндпоинты сервиса: POST /triage (основной) и GET /health."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core import triage_service
from app.db import database
from app.logging_setup import get_logger
from app.schemas import TriageRequest, TriageResponse

logger = get_logger(__name__)

router = APIRouter()


@router.post("/triage", response_model=TriageResponse)
def triage(payload: TriageRequest) -> TriageResponse:
    """Принимает обращение, классифицирует, пишет черновик ответа и сохраняет в БД.

    - 429: превышен лимит запросов для client_id;
    - 500: ошибка записи в журнал аудита.
    Сбой LLM фолбэком превращается в 200 с escalate=true.
    """
    try:
        return triage_service.process_triage(payload)
    except triage_service.RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов: превышен лимит для данного client_id. Попробуйте позже.",
        )
    except triage_service.StorageError:
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка: не удалось сохранить запись. Попробуйте позже.",
        )


@router.get("/health")
def health() -> JSONResponse:
    """Проверка работоспособности сервиса и доступности базы данных."""
    db_ok = database.db_healthcheck()
    logger.info("Health-check: db=%s", "ok" if db_ok else "error")
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "error"},
    )