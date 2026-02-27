# -*- coding: utf-8 -*-
"""Высокопроизводительное сопоставление целевых индикаторов (Aho-Corasick)."""

from __future__ import annotations

import logging

from app.config import Config
from app.darknet.models import DarknetPost

logger = logging.getLogger(__name__)

try:
    import ahocorasick as _ahocorasick
except Exception:  # pragma: no cover
    _ahocorasick = None


class _FallbackAutomaton:
    """Минимальный fallback, если pyahocorasick недоступен в окружении."""

    def __init__(self):
        self._words: list[tuple[str, tuple[int, str]]] = []

    def add_word(self, word: str, value: tuple[int, str]) -> None:
        self._words.append((word, value))

    def make_automaton(self) -> None:
        return None

    def iter(self, text: str):
        for word, value in self._words:
            start = 0
            while True:
                idx = text.find(word, start)
                if idx == -1:
                    break
                yield idx + len(word) - 1, value
                start = idx + 1


class TargetAutomaton:
    def __init__(self, target_list: list[str]):
        """Инициализирует префиксное дерево для O(N) поиска."""
        if _ahocorasick is None:
            logger.warning("pyahocorasick недоступен, используется fallback-автомат (медленнее).")
            self.automaton = _FallbackAutomaton()
        else:
            self.automaton = _ahocorasick.Automaton()

        prepared_targets = [item.strip().lower() for item in (target_list or []) if item and item.strip()]
        for idx, target in enumerate(prepared_targets):
            self.automaton.add_word(target, (idx, target))

        self.automaton.make_automaton()
        logger.info("Aho-Corasick автомат скомпилирован для %s целей.", len(prepared_targets))

    def find_matches(self, text_chunk: str) -> set[str]:
        """Пробегает по строке дампа за O(N) и возвращает найденные цели."""
        found_targets: set[str] = set()
        text_lower = (text_chunk or "").lower()

        for _end_index, (_idx, original_target) in self.automaton.iter(text_lower):
            found_targets.add(original_target)

        return found_targets


class TargetMatcher:
    """Совместимый интерфейс для поиска целей в посте."""

    def __init__(self):
        targets = [
            *(Config.TARGET_EMAILS or []),
            *(Config.TARGET_DOMAINS or []),
        ]
        self.automaton = TargetAutomaton(targets)

    def find_matches(self, post: DarknetPost) -> list[dict]:
        content = post.content or ""
        found = self.automaton.find_matches(content)
        return [{"type": "target_match", "value": target, "context": "matched_by_aho_corasick"} for target in sorted(found)]
