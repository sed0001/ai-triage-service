"""Точка входа FastAPI-приложения.

Здесь регистрируются роуты, lifespan (инициализация БД/логгеров),
middleware аудита HTTP-запросов и глобальные обработчики ошибок,
которые возвращают понятные сообщения вместо технического стека.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import routes
from app.config import settings
from app.db import database
from app.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Действия при старте и остановке приложения."""
    setup_logging()
    database.init_db()
    logger.info(
        "Сервис запущен: host=%s port=%s model=%s llm_base_url=%s rate_limit=%s/мин",
        settings.app_host,
        settings.app_port,
        settings.llm_model,
        settings.llm_base_url,
        settings.rate_limit_per_minute,
    )
    if not settings.llm_api_key:
        logger.error("LLM_API_KEY не задан — /triage будет возвращать фолбэк «передано оператору»")
    yield
    logger.info("Сервис остановлен")


# FastAPI-приложение: единая точка входа для Uvicorn
app = FastAPI(
    title="AI Triage Service",
    description="MVP-сервис первичной обработки обращений поддержки: классификация, черновик ответа, аудит.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(routes.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Пишет каждый HTTP-запрос в logs/requests.log с длительностью."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logging.getLogger("requests").info(
        "%s %s -> %s (%.0f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Понятное сообщение 422: перечисляем поля и причины ошибок."""
    errors = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []) if part != "body")
        errors.append(
            {
                "field": loc or "request",
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    logger.error("Ошибка валидации %s: %s", request.url.path, errors)
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Перехват HTTPException: логируем 5xx, остальное отдаём как есть."""
    if exc.status_code >= 500:
        logger.error("HTTP %s на %s: %s", exc.status_code, request.url.path, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Финальная страховка: не раскрываем детали стека пользователю."""
    logger.error("Необработанная ошибка на %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера. Попробуйте позже."},
    )