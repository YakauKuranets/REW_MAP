# -*- coding: utf-8 -*-
"""Вероятностный генератор паролей на основе упрощённой PCFG модели."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterator, List


class PCFGGenerator:
    """Генерирует кандидаты по вероятностным шаблонам для authorised аудита."""

    def __init__(self) -> None:
        self.structures: Dict[str, float] = {}
        self.digit_sequences: Dict[str, float] = {}
        self.letter_sequences: Dict[str, float] = {}

    def train(self, passwords: List[str]) -> None:
        """Обучает упрощённую модель на наборе паролей."""
        clean = [pwd.strip() for pwd in passwords if pwd and pwd.strip()]
        if not clean:
            self.structures = {}
            self.digit_sequences = {}
            self.letter_sequences = {}
            return

        structure_counter = defaultdict(int)
        digit_counter = defaultdict(int)
        letter_counter = defaultdict(int)

        for pwd in clean:
            structure: List[str] = []
            digit_seq: List[str] = []
            letters_count = 0

            for char in pwd:
                if char.isalpha():
                    structure.append("L")
                    letters_count += 1
                elif char.isdigit():
                    structure.append("D")
                    digit_seq.append(char)
                else:
                    structure.append("S")

            structure_counter["".join(structure)] += 1
            if digit_seq:
                digit_counter["".join(digit_seq)] += 1
            if letters_count:
                letter_counter[f"L{letters_count}"] += 1

        total = len(clean) or 1
        self.structures = {k: v / total for k, v in structure_counter.items()}

        digit_total = sum(digit_counter.values()) or 1
        self.digit_sequences = {k: v / digit_total for k, v in digit_counter.items()} if digit_counter else {}

        letter_total = sum(letter_counter.values()) or 1
        self.letter_sequences = {k: v / letter_total for k, v in letter_counter.items()} if letter_counter else {}

    def generate_candidates(self, base_words: List[str], count: int = 100) -> Iterator[str]:
        """Генерирует кандидаты на основе наиболее вероятных структур."""
        if not self.structures:
            return iter([])

        top_structures = sorted(
            self.structures.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]

        candidates: List[str] = []
        for word in base_words[:10]:
            base = (word or "").strip()
            if not base:
                continue
            for structure, _ in top_structures:
                assembled: List[str] = []
                letter_pos = 0
                for char_type in structure:
                    if char_type == "L":
                        if letter_pos < len(base):
                            assembled.append(base[letter_pos])
                            letter_pos += 1
                        else:
                            assembled.append("a")
                    elif char_type == "D":
                        if self.digit_sequences:
                            likely_digits = max(self.digit_sequences.items(), key=lambda item: item[1])[0]
                            assembled.append(likely_digits[:1])
                        else:
                            assembled.append("1")
                    else:
                        assembled.append("!")
                candidates.append("".join(assembled))
                if len(candidates) >= count:
                    return iter(list(dict.fromkeys(candidates[:count])))

        return iter(list(dict.fromkeys(candidates[:count])))

    def generate(self, base_words: List[str], limit: int = 2000) -> List[str]:
        """Совместимость с текущим кодом: train+generate в одном вызове."""
        # Небольшой встроенный корпус для структуры, если внешний не передан.
        bootstrap = [
            "admin123",
            "password123",
            "qwerty123",
            "router2024",
            "wifi@home",
            "guest1234",
        ]
        self.train(bootstrap)
        return list(self.generate_candidates(base_words, count=limit))
