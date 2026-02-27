# -*- coding: utf-8 -*-
"""Utilities for optimized password dictionary loading and filtering."""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
from typing import Iterator, List

logger = logging.getLogger(__name__)


class DictionaryOptimizer:
    """Load, filter and cache dictionary candidates for authorised audits."""

    def __init__(self, wordlists_path: str = "/data/wordlists") -> None:
        self.wordlists_path = Path(wordlists_path)
        self.cached_passwords: List[str] = []
        self.cached_weights: List[float] = []

    def load_optimized_dictionary(
        self,
        min_length: int = 8,
        max_length: int = 63,
        require_mixed: bool = False,
        top_n: int = 10000,
    ) -> List[str]:
        """Load rockyou-based dictionary with basic filtering and dedup."""
        rockyou_path = self.wordlists_path / "rockyou.txt"

        if not rockyou_path.exists():
            gz_path = self.wordlists_path / "rockyou.txt.gz"
            if gz_path.exists():
                with gzip.open(gz_path, "rt", encoding="latin-1", errors="ignore") as handle:
                    passwords = handle.readlines()
            else:
                logger.warning("rockyou dictionary not found in %s", self.wordlists_path)
                self.cached_passwords = self._get_fallback_dictionary()
                return self.cached_passwords
        else:
            with rockyou_path.open("r", encoding="latin-1", errors="ignore") as handle:
                passwords = handle.readlines()

        filtered: List[str] = []
        for item in passwords:
            pwd = item.strip()
            if not pwd:
                continue
            if len(pwd) < min_length or len(pwd) > max_length:
                continue
            if require_mixed:
                has_digit = any(ch.isdigit() for ch in pwd)
                has_alpha = any(ch.isalpha() for ch in pwd)
                if not (has_digit and has_alpha):
                    continue
            filtered.append(pwd)
            if len(filtered) >= top_n:
                break

        self.cached_passwords = list(dict.fromkeys(filtered))
        logger.info("Loaded %s optimized passwords", len(self.cached_passwords))
        return self.cached_passwords

    def get_weighted_passwords(self, count: int = 1000) -> Iterator[str]:
        """Yield passwords ordered by Zipf-like weight (most probable first)."""
        if not self.cached_passwords:
            self.load_optimized_dictionary()

        self.cached_weights.clear()
        for index, pwd in enumerate(self.cached_passwords[:count]):
            self.cached_weights.append(1.0 / (index + 1))
            yield pwd

    def get_wifi_specific_dictionary(self) -> List[str]:
        """Router and Wi‑Fi specific weak candidates."""
        wifi_dict = [
            "admin", "password", "12345678", "wireless", "network",
            "linksys", "netgear", "dlink", "tp-link", "asus",
            "12345670", "12345678", "00000000", "11111111", "22222222",
            "33333333", "44444444", "55555555", "66666666", "88888888",
            "default", "guest", "changeme", "password123", "admin123",
        ]
        return list(dict.fromkeys(wifi_dict))

    def _get_fallback_dictionary(self) -> List[str]:
        return [
            "admin", "12345678", "password", "1234567890", "qwertyui",
            "admin123", "letmein", "welcome", "monkey", "dragon",
            "football", "baseball", "master", "superman", "batman",
        ]
