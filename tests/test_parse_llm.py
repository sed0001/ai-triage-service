"""Тесты разбора JSON-ответа языковой модели."""

import pytest

from app.core.llm import LLMError, parse_json_result


def test_plain_json():
    raw = '{"category": "billing", "draft_reply": "ответ", "confidence": "high", "escalate": false}'
    data = parse_json_result(raw)
    assert data["category"] == "billing"
    assert data["escalate"] is False


def test_message_with_markdown_fence():
    raw = '```json\n{"category": "support", "draft_reply": "ok", "confidence": "medium", "escalate": true}\n```'
    data = parse_json_result(raw)
    assert data["category"] == "support"
    assert data["escalate"] is True


def test_extra_text_around_json():
    raw = 'Вот результат:\n{"category": "complaint", "draft_reply": "спасибо", "confidence": "low", "escalate": true}\nКонец.'
    data = parse_json_result(raw)
    assert data["category"] == "complaint"


def test_missing_required_field_raises():
    with pytest.raises(LLMError):
        parse_json_result('{"category": "support", "confidence": "high"}')


def test_garbage_raises():
    with pytest.raises(LLMError):
        parse_json_result("модель вообще не вернула json")