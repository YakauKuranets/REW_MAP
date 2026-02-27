# -*- coding: utf-8 -*-
"""Частотный анализ паролей для выбора наиболее вероятных кандидатов."""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Tuple


class FrequencyAnalyzer:
    """Анализ частотности символов, паттернов и слов в паролях."""

    def __init__(self) -> None:
        self.character_freq: Dict[str, float] = {}
        self.pattern_freq: Dict[str, float] = {}
        self.word_freq: Dict[str, float] = {}

    def analyze_passwords(self, passwords: List[str]) -> None:
        """Вычисляет распределения символов, паттернов и слов."""
        clean_passwords = [pwd.strip() for pwd in passwords if pwd and pwd.strip()]
        if not clean_passwords:
            self.character_freq = {}
            self.pattern_freq = {}
            self.word_freq = {}
            return

        char_counter = Counter()
        for pwd in clean_passwords:
            char_counter.update(pwd.lower())

        total_chars = sum(char_counter.values()) or 1
        self.character_freq = {
            char: count / total_chars
            for char, count in char_counter.items()
        }

        pattern_map = {
            "alpha": 0,
            "digit": 0,
            "special": 0,
            "upper": 0,
        }
        for pwd in clean_passwords:
            for char in pwd:
                if char.isupper():
                    pattern_map["upper"] += 1
                if char.isalpha():
                    pattern_map["alpha"] += 1
                elif char.isdigit():
                    pattern_map["digit"] += 1
                else:
                    pattern_map["special"] += 1

        total_patterns = sum(pattern_map.values()) or 1
        self.pattern_freq = {
            key: value / total_patterns
            for key, value in pattern_map.items()
        }

        common_words = [
            "admin", "user", "pass", "root", "guest",
            "home", "office", "work", "family", "wifi",
        ]
        word_counter = Counter()
        for pwd in clean_passwords:
            pwd_lower = pwd.lower()
            for word in common_words:
                if word in pwd_lower:
                    word_counter[word] += 1

        total_words = sum(word_counter.values()) or 1
        self.word_freq = {
            word: count / total_words
            for word, count in word_counter.most_common()
        }

    def get_most_probable_mutations(self, base_word: str, count: int = 10) -> List[str]:
        """Генерирует вероятные мутации на основе простой статистики."""
        base = (base_word or "").strip()
        if not base:
            return []

        mutations: List[str] = []
        years = ["2025", "2024", "2023", "2022", "2021", "2020"]
        endings = ["123", "1234", "12345", "111", "000", "321"]

        for year in years:
            mutations.append(f"{base}{year}")

        for ending in endings:
            mutations.append(f"{base}{ending}")

        if self.pattern_freq.get("upper", 0.0) > 0.1:
            mutations.extend([base.capitalize(), base.upper()])

        leet_map = {
            "a": ["@", "4"],
            "e": ["3"],
            "i": ["1", "!"],
            "o": ["0"],
            "s": ["5", "$"],
            "t": ["7"],
        }
        for char, replacements in leet_map.items():
            if char in base.lower():
                for repl in replacements:
                    mutations.append(base.lower().replace(char, repl))

        return list(dict.fromkeys(mutations))[:count]

    def top_n(self, passwords: Iterable[str], n: int = 1000) -> List[Tuple[str, int]]:
        """Совместимость: возвращает top-N по частоте."""
        counter = Counter(p.strip() for p in passwords if p and p.strip())
        return counter.most_common(n)

    def zipf_ranked(self, passwords: Iterable[str], n: int = 1000) -> List[str]:
        """Совместимость: Zipf-like сортировка по убыванию частоты."""
        return [pwd for pwd, _ in self.top_n(passwords, n=n)]
