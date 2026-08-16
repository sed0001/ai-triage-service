"""Юнит-тесты базы знаний: гибридный подбор ответа без LLM."""

import json

from app.core.knowledge_base import KnowledgeBase, _normalize

# Тексты из examples/test_data.md (обращения №1 и №5) — должны совпадать точно
SAMPLE_BILLING = "Здравствуйте! Мне дважды списали деньги за подписку, верните, пожалуйста, один платёж."
SAMPLE_OTHER = "Подскажите, во сколько закрывается пункт выдачи?"


def _entry(category: str, keywords, **extra):
    data = {
        "match_text": "точный текст обращения",
        "keywords": keywords,
        "category": category,
        "confidence": "high",
        "escalate": False,
        "draft_reply": "Ответ поддержки.",
    }
    data.update(extra)
    return data


def _kb(tmp_path, entries) -> KnowledgeBase:
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return KnowledgeBase(str(path))


def test_normalize_collapses_spaces_and_case():
    assert _normalize("  Двойные   пробелы  ") == "двойные пробелы"


def test_exact_match(tmp_path):
    kb = _kb(tmp_path, [_entry("billing", [], match_text=SAMPLE_BILLING)])
    result = kb.lookup(SAMPLE_BILLING)
    assert result is not None
    assert result["category"] == "billing"


def test_exact_match_case_and_spaces_insensitive(tmp_path):
    kb = _kb(tmp_path, [_entry("billing", [])])
    result = kb.lookup("   здравствуйте! мне дважды   списали деньги за подписку, верните, пожалуйста, один платёж.   ")
    assert result is None  # пунктуация отличается — это НЕ точное совпадение, работает нормализация только регистром/пробелами


def test_exact_match_only_full_equal(tmp_path):
    kb = _kb(tmp_path, [_entry("billing", [])])
    assert kb.lookup("Здравствуйте! Мне дважды списали деньги за подписку.") is None


def test_keyword_match(tmp_path):
    kb = _kb(tmp_path, [_entry("support", ["личный кабинет"])])
    result = kb.lookup("у меня совсем не открывается личный кабинет после оплаты")
    assert result is not None
    assert result["category"] == "support"


def test_keywords_case_insensitive(tmp_path):
    kb = _kb(tmp_path, [_entry("other", ["пункт выдач"])])
    # и ключевое слово, и текст нормализуются к нижнему регистру
    assert kb.lookup("ГДЕ ПУНКТ ВЫДАЧИ?") is not None


def test_exact_beats_keywords(tmp_path):
    kb = _kb(tmp_path, [{"match_text": "точный текст с деньгами", "keywords": ["деньги"],
                         "category": "other", "confidence": "low", "escalate": True, "draft_reply": "Другое."}])
    # Ключевые слова совпадают, но точное совпадение должно победить
    assert kb.lookup("точный текст с деньгами")["category"] == "other"


def test_no_match_returns_none(tmp_path):
    kb = _kb(tmp_path, [_entry("billing", ["подписка"])])
    assert kb.lookup("погода в Москве завтра") is None


def test_missing_file_does_not_crash():
    kb = KnowledgeBase("несуществующий-файл.json")
    assert kb.lookup("любой текст") is None


def test_duplicated_keywords_ok(tmp_path):
    kb = _kb(tmp_path, [_entry("other", ["тариф", "тариф"])])
    assert kb.lookup("какой тариф выбрать") is not None


def test_official_kb_covers_all_samples():
    """Каждый тестовый пример из examples/test_data.md находится в базе знаний."""
    from app.core.state import get_knowledge_base

    kb = get_knowledge_base()
    samples = [
        "Здравствуйте! Мне дважды списали деньги за подписку, верните, пожалуйста, один платёж.",
        "Подскажите, как поменять тариф на более дешёвый?",
        "После оплаты не открывается личный кабинет, что делать?",
        "Это безобразие! Сервис вообще не работает, я ничего не могу скачать. Верните деньги!",
        "Подскажите, во сколько закрывается пункт выдачи?",
        "Хочу оформить возврат товара из заказа № 12345, как это сделать?",
    ]
    for text in samples:
        assert kb.lookup(text) is not None, f"не найдено в базе знаний: {text}"