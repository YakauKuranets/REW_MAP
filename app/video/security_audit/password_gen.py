from __future__ import annotations

from itertools import islice
from typing import Iterator, Optional


class PasswordGenerator:
    COMMON = [
        "admin",
        "12345",
        "password",
        "123456",
        "12345678",
        "1234",
        "root",
        "user",
        "service",
        "hik12345",
        "hikvision",
        "dahua",
        "admin123",
        "Admin@123",
        "123456789",
        "1111",
        "abc123",
        "camera",
        "ipcam",
        "default",
        "system",
        "manager",
        "support",
    ]

    def __init__(self, vendor: Optional[str] = None):
        self.vendor = vendor.lower() if vendor else None
        self.custom_wordlist: Optional[list[str]] = None

    def set_wordlist(self, wordlist: list[str]) -> None:
        self.custom_wordlist = [w.strip() for w in wordlist if w and w.strip()] or None

    def _generate_mutations(self, base_words: list[str]) -> Iterator[str]:
        years = [str(y) for y in range(2020, 2027)]
        for p in base_words:
            for y in years:
                yield f"{p}{y}"
                yield f"{p}@{y}"
            yield p.capitalize()
            yield p.upper()

    def generate(self, limit: int = 10000) -> Iterator[str]:
        words = self.custom_wordlist if self.custom_wordlist is not None else self.COMMON

        def stream() -> Iterator[str]:
            seen: set[str] = set()
            for pwd in words:
                if pwd not in seen:
                    seen.add(pwd)
                    yield pwd
            for pwd in self._generate_mutations(words):
                if pwd not in seen:
                    seen.add(pwd)
                    yield pwd
            if self.vendor:
                vendor_words = [f"{self.vendor}123", f"{self.vendor}@2025", f"{self.vendor}admin"]
                for pwd in vendor_words:
                    if pwd not in seen:
                        seen.add(pwd)
                        yield pwd

        return islice(stream(), max(1, int(limit)))
