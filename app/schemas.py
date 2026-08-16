"""Pydantic-модели контракта POST /triage: вход и выход."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["billing", "support", "complaint", "other"]
Channel = Literal["email", "form", "chat"]
Confidence = Literal["high", "medium", "low"]


class TriageRequest(BaseModel):
    """Входной JSON POST /triage."""

    # Обязательное поле: 1..2000 символов
    text: str = Field(min_length=1, max_length=2000, description="Текст обращения")
    # Метка источника (для аналитики), реальная интеграция не подключается
    channel: Channel = Field(description="Канал обращения: email, form или chat")
    # Идентификатор клиента: используется для лимитирования и аудита
    client_id: str = Field(min_length=1, max_length=128, description="Идентификатор клиента")

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        """Отсекаем пробелы по краям до проверки ограничений длины."""
        if isinstance(value, str):
            return value.strip()
        return value


class TriageResponse(BaseModel):
    """Выходной JSON POST /triage."""

    category: Category
    draft_reply: str = Field(min_length=1, max_length=2000, description="Черновик ответа 1–6 предложений")
    confidence: Confidence
    escalate: bool