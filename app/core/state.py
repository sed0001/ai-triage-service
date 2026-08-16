"""Общие синглтоны приложения: лимитер, клиент LLM и база знаний.

Вынесены в отдельный модуль, чтобы роуты (app.api.routes) не тянули
зависимости на фреймверк и наоборот.
"""

from app.config import settings
from app.core.knowledge_base import KnowledgeBase
from app.core.llm import LLMService
from app.core.rate_limiter import SlidingWindowRateLimiter

_rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
_llm = LLMService()
_knowledge_base = KnowledgeBase(settings.knowledge_base_path)


def get_rate_limiter() -> SlidingWindowRateLimiter:
    return _rate_limiter


def get_llm() -> LLMService:
    return _llm


def get_knowledge_base() -> KnowledgeBase:
    return _knowledge_base