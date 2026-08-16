"""Интеграционные тесты API: валидация входа, демо-режим базы знаний, лимит, health.

Без заданного LLM_API_KEY сервис работает в демо-режиме базы знаний:
совпадения из examples/knowledge_base.json возвращают свои ответы,
прочий текст — общий шаблон с эскалацией. Сеть не нужна.
"""

from app.core.llm import FALLBACK_REPLY

# Текст из examples/test_data.md (обращение №1) — точное совпадение в базе знаний
SAMPLE_BILLING = "Здравствуйте! Мне дважды списали деньги за подписку, верните, пожалуйста, один платёж."


def test_missing_text(client):
    resp = client.post("/triage", json={"channel": "email", "client_id": "c-1"})
    assert resp.status_code == 422


def test_empty_text_after_spaces(client):
    resp = client.post("/triage", json={"text": "   ", "channel": "email", "client_id": "c-1"})
    assert resp.status_code == 422


def test_text_too_long(client):
    resp = client.post("/triage", json={"text": "x" * 2001, "channel": "email", "client_id": "c-1"})
    assert resp.status_code == 422


def test_invalid_channel(client):
    resp = client.post("/triage", json={"text": "привет", "channel": "phone", "client_id": "c-1"})
    assert resp.status_code == 422


def test_missing_client_id(client):
    resp = client.post("/triage", json={"text": "привет", "channel": "email"})
    assert resp.status_code == 422


def test_validation_error_is_understandable(client):
    resp = client.post("/triage", json={"channel": "email", "client_id": "c-1"})
    body = resp.json()
    assert "detail" in body
    assert any("text" in str(err.get("field")) for err in body["detail"])


def test_valid_request_returns_template_when_no_match(client):
    """Без ключа и без совпадения в базе знаний — шаблон с эскалацией."""
    resp = client.post(
        "/triage",
        json={"text": "Просто проверка демо-режима", "channel": "email", "client_id": "c-fallback"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["escalate"] is True
    assert data["confidence"] == "low"
    assert data["category"] == "other"
    assert data["draft_reply"] == FALLBACK_REPLY


def test_knowledge_base_exact_match(client):
    """Тексты из тестовых данных воспроизводятся из базы знаний без ключа."""
    resp = client.post("/triage", json={"text": SAMPLE_BILLING, "channel": "email", "client_id": "k-exact"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "billing"
    assert data["confidence"] == "medium"
    assert data["escalate"] is False
    assert "платёж" in data["draft_reply"]


def test_knowledge_base_keyword_match(client):
    """Совпадение по ключевым словам тоже возвращает запись из базы знаний."""
    resp = client.post("/triage", json={"text": "опять дважды списали деньги с карты", "channel": "chat", "client_id": "k-keyword"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "billing"


def test_knowledge_base_complaint_escalates(client):
    """Эмоциональная жалоба из базы знаний размечена escalate=true."""
    resp = client.post(
        "/triage",
        json={"text": "Это безобразие! Сервис вообще не работает, я ничего не могу скачать. Верните деньги!", "channel": "email", "client_id": "k-complaint"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "complaint"
    assert data["escalate"] is True


def test_rate_limit_exceeded(client):
    """При лимите 5/мин шестой запрос для одного client_id отклоняется."""
    taxpayer = "c-burst"
    for _ in range(5):
        resp = client.post("/triage", json={"text": "тест", "channel": "chat", "client_id": taxpayer})
        assert resp.status_code == 200
    resp = client.post("/triage", json={"text": "тест 6", "channel": "chat", "client_id": taxpayer})
    assert resp.status_code == 429


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"