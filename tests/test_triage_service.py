"""Юнит-тесты бизнес-правил: нормализация ответа модели, эскалация и выбор режима."""

import pytest

from app.config import settings
from app.core.llm import LLMError
from app.core.triage_service import _build_response, process_triage
from app.db import database
from app.schemas import TriageRequest

# Текст обращения №1 из examples/test_data.md — есть и в базе знаний
SAMPLE_BILLING = "Здравствуйте! Мне дважды списали деньги за подписку, верните, пожалуйста, один платёж."


@pytest.fixture()
def clean_db(tmp_path, monkeypatch):
    """Изолированная БД для тестов полного цикла process_triage."""
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "tickets_test.db"))
    monkeypatch.setattr(database, "_initialized", False)
    database.init_db()
    return database


def test_normalizes_category_and_confidence():
    """Ответ модели приводится к нижнему регистру без пробелов."""
    result = _build_response(
        {"category": " BILLING ", "draft_reply": "  Верните деньги  ", "confidence": "High", "escalate": False}
    )
    assert result.category == "billing"
    assert result.confidence == "high"
    assert result.escalate is False


def test_escalation_forced_when_confidence_is_low():
    """При низкой уверенности обращение передаётся человеку, даже если модель не поставила флаг."""
    result = _build_response(
        {"category": "support", "draft_reply": "Уточните, пожалуйста, детали.", "confidence": "low", "escalate": False}
    )
    assert result.escalate is True


def test_invalid_category_raises():
    with pytest.raises(LLMError):
        _build_response({"category": "refund", "draft_reply": "ok", "confidence": "high", "escalate": False})


def test_missing_category_raises():
    with pytest.raises(LLMError):
        _build_response({"draft_reply": "ok", "confidence": "high", "escalate": False})


def test_invalid_confidence_raises():
    with pytest.raises(LLMError):
        _build_response({"category": "other", "draft_reply": "ok", "confidence": "sure", "escalate": False})


def test_empty_draft_raises():
    with pytest.raises(LLMError):
        _build_response({"category": "other", "draft_reply": "   ", "confidence": "high", "escalate": False})


def test_with_key_uses_llm_not_knowledge_base(clean_db, monkeypatch):
    """При заданном ключе работает LLM, даже если текст совпадает с базой знаний."""
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")

    class FakeLLM:
        def classify(self, text):
            return {"category": "billing", "draft_reply": "Из модели.", "confidence": "high", "escalate": False}

    # triage_service вызывает get_llm по имени, импортированному в свой модуль
    monkeypatch.setattr("app.core.triage_service.get_llm", lambda: FakeLLM())
    result = process_triage(TriageRequest(text=SAMPLE_BILLING, channel="email", client_id="c-llm"))
    assert result.category == "billing"
    # Ответ именно от модели, а не из knowledge_base.json
    assert result.draft_reply == "Из модели."


def test_without_key_skips_llm_and_uses_knowledge_base(clean_db, monkeypatch):
    """Без ключа LLM не вызывается вовсе — работает демо-режим базы знаний."""
    monkeypatch.setattr(settings, "llm_api_key", "")

    calls = {"count": 0}

    class SpyLLM:
        def classify(self, text):
            calls["count"] += 1
            raise AssertionError("LLM не должен вызываться без ключа")

    monkeypatch.setattr("app.core.triage_service.get_llm", lambda: SpyLLM())
    result = process_triage(TriageRequest(text=SAMPLE_BILLING, channel="email", client_id="c-kb"))
    assert calls["count"] == 0
    assert result.category == "billing"
    assert "платёж" in result.draft_reply  # ответ из knowledge_base.json