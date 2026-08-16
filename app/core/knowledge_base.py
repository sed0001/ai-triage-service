"""Локальная «база знаний» для демонстрации работы без LLM.

Когда переменная LLM_API_KEY не задана, сервис подбирает готовый ответ
из файла examples/knowledge_base.json вместо вызова языковой модели:
сначала точное совпадение текста обращения, затем по ключевым словам.
Если совпадения нет — возвращается None, и сервис отдаёт общий шаблон.

Это позволяет прогнать демо с тестовыми обращениями совсем без ключа
и без обращения к сети: ответы для `examples/test_data.md` воспроизводятся
один в один, а произвольный текст всё равно получает честный шаблон.
"""

import json
import re
from pathlib import Path

from app.logging_setup import get_logger

logger = get_logger(__name__)


def _normalize(text: str) -> str:
    """Приводит текст к единому виду: нижний регистр, без лишних пробелов."""
    return re.sub(r"\s+", " ", text.strip().lower())


class KnowledgeBase:
    """Загружает записи из JSON и подбирает ответ по тексту обращения."""

    def __init__(self, path: str) -> None:
        self._exact: list[tuple[str, dict]] = []
        self._keywords: list[tuple[tuple[str, ...], dict]] = []

        try:
            entries = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("База знаний не загружена (%s): %s", path, exc)
            entries = []

        for entry in entries:
            raw_text = str(entry.get("match_text") or "").strip()
            if raw_text:
                self._exact.append((_normalize(raw_text), entry))
            words = [str(word).strip() for word in entry.get("keywords") or [] if str(word).strip()]
            if words:
                self._keywords.append((tuple(word.lower() for word in words), entry))

    def lookup(self, text: str) -> dict | None:
        """Возвращает запись из базы знаний или None.

        Приоритет: точное совпадение текста, затем первое вхождение
        любого из ключевых слов (в порядке записей в файле).
        """
        norm = _normalize(text)
        for key, entry in self._exact:
            if key == norm:
                return entry
        for words, entry in self._keywords:
            if any(word in norm for word in words):
                return entry
        return None