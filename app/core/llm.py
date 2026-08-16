"""Клиент языковой модели через OpenAI-совместимый эндпоинт ProxyAPI.

Включает вызов chat.completions, устойчивый разбор JSON-ответа модели
и собственное исключение LLMError для сценария «если всё сломалось».
"""

import json
import re

from openai import OpenAI

from app.config import settings
from app.core import prompts
from app.logging_setup import get_logger

logger = get_logger(__name__)

# Шаблонный ответ при сбое LLM или невалидном ответе модели
FALLBACK_REPLY = "Ваш запрос передан оператору поддержки. Мы свяжемся с вами в ближайшее время."

_REQUIRED_FIELDS = ("category", "draft_reply", "confidence", "escalate")


class LLMError(Exception):
    """Ошибка вызова LLM или ответ, не соответствующий JSON-контракту."""


class LLMService:
    """Обёртка над OpenAI-совместимым API. Клиент создаётся лениво."""

    def __init__(self) -> None:
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        api_key = settings.llm_api_key.strip()
        if not api_key:
            raise LLMError("Не задан API-ключ LLM (переменная окружения LLM_API_KEY)")
        if self._client is None:
            self._client = OpenAI(
                api_key=api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
            )
        return self._client

    def classify(self, text: str) -> dict:
        """Отправляет обращение модели и возвращает распарсенный JSON-ответ.

        При любом сбое вызова или невалидном ответе поднимает LLMError.
        """
        client = self._get_client()
        try:
            completion = client.chat.completions.create(
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                messages=[
                    {"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": prompts.build_user_message(text)},
                ],
            )
        except Exception as exc:  # сетевые ошибки, таймауты, ошибки 4xx/5xx провайдера
            logger.error("Ошибка вызова LLM API: %s", exc)
            raise LLMError(f"Ошибка вызова LLM API: {exc}") from exc

        content = completion.choices[0].message.content or ""
        return parse_json_result(content)


def _extract_json_block(raw: str) -> str:
    """Вырезает JSON-объект из текста, срезая markdown-ограждения и пояснения."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError("В ответе модели не найден JSON-объект")
    return text[start : end + 1]


def parse_json_result(raw: str) -> dict:
    """Превращает текст ответа модели в словарь и проверяет обязательные поля."""
    try:
        data = json.loads(_extract_json_block(raw))
    except (json.JSONDecodeError, LLMError) as exc:
        logger.error("Не удалось распарсить ответ LLM (ответ: %.300s)", raw)
        raise LLMError("Модель вернула ответ, не соответствующий JSON-контракту") from exc
    missing = [field for field in _REQUIRED_FIELDS if field not in data]
    if missing:
        logger.error("В ответе модели отсутствуют поля: %s", ", ".join(missing))
        raise LLMError(f"В ответе модели отсутствуют поля: {', '.join(missing)}")
    return data