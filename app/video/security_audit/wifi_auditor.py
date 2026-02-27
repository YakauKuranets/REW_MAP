from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .dictionary_optimizer import DictionaryOptimizer
from .frequency_analyzer import FrequencyAnalyzer
from .pcfg_generator import PCFGGenerator

logger = logging.getLogger(__name__)


ProgressCallback = Optional[Callable[[str, Dict[str, Any]], None]]


class WifiAuditor:
    """
    Аудитор безопасности Wi‑Fi в рамках authorized тестирования.

    Реальная эксплуатация не выполняется: проверка строится на:
    - слабых типах шифрования (OPEN/WEP),
    - эвристиках по OUI (WPS risk),
    - словаре вероятных слабых паролей (симуляция проверки).
    """

    DEFAULT_PASSWORDS = [
        "12345678", "password", "admin", "12345", "1234567890",
        "11111111", "88888888", "00000000", "1234", "123456",
        "qwertyui", "asdfghjk", "zxcvbnm", "passw0rd", "admin123",
        "default", "user", "guest", "root", "support",
    ]

    REGION_PASSWORD_SEEDS = {
        "ru": ["qwerty123", "пароль123", "wifi12345", "adminadmin", "123qweasd"],
        "en": ["welcome123", "companywifi", "changeme", "admin2024", "letmein123"],
    }

    WPS_PINS = [
        "12345670", "12345678", "00000000", "11111111", "22222222",
        "33333333", "44444444", "55555555", "66666666", "77777777",
        "88888888", "99999999", "98765432", "87654321", "13579246",
    ]

    def __init__(self, region: str = "ru") -> None:
        self.region = (region or "ru").lower()
        self.dictionary = self._load_dictionary()

    def audit(
        self,
        bssid: str,
        essid: str,
        security_type: str | None,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        """Выполняет проверку безопасности с оптимизированным словарём и PCFG."""
        sec = (security_type or "").upper()
        essid_safe = essid or ""
        started_at = time.time()

        if sec == "OPEN":
            return {
                "is_vulnerable": True,
                "vulnerability_type": "OPEN_NETWORK",
                "password": None,
                "details": {
                    "status": "completed",
                    "message": "Сеть не защищена паролем.",
                    "progress": 100,
                    "estimatedTime": 0,
                    "method": "security_type_check",
                    "executionTime": 0,
                },
            }

        if sec == "WEP":
            return {
                "is_vulnerable": True,
                "vulnerability_type": "WEP",
                "password": None,
                "details": {
                    "status": "completed",
                    "message": "Устаревший протокол WEP — легко взламывается.",
                    "progress": 100,
                    "estimatedTime": 0,
                    "method": "security_type_check",
                    "executionTime": 0,
                },
            }

        dict_optimizer = DictionaryOptimizer(wordlists_path=str(Path(__file__).parent / "wordlists"))
        freq_analyzer = FrequencyAnalyzer()
        pcfg_gen = PCFGGenerator()

        optimized_dict = dict_optimizer.load_optimized_dictionary(
            min_length=8,
            max_length=63,
            require_mixed=True,
            top_n=10000,
        )
        wifi_dict = dict_optimizer.get_wifi_specific_dictionary()
        combined_dict = list(dict.fromkeys(wifi_dict + optimized_dict))

        # Частотный профиль словаря для потенциальных мутаций/приоритезации.
        freq_analyzer.analyze_passwords(combined_dict[:2000])
        base_word = essid_safe.split(".")[0] if essid_safe else "network"
        mutations = freq_analyzer.get_most_probable_mutations(base_word, count=30)

        pcfg_gen.train(combined_dict[:1000])
        candidates = list(
            pcfg_gen.generate_candidates(
                base_words=["admin", "user", base_word, *mutations[:5]],
                count=500,
            )
        )

        final_list = list(dict.fromkeys(combined_dict + candidates + mutations + self.REGION_PASSWORD_SEEDS.get(self.region, [])))
        total = max(len(final_list), 1)
        estimated_time = self._estimate_time_seconds(total)

        result: Dict[str, Any] = {
            "is_vulnerable": False,
            "vulnerability_type": None,
            "password": None,
            "details": {
                "status": "running",
                "message": "Выполняется анализ сети.",
                "bssid": bssid,
                "essid": essid_safe,
                "region": self.region,
                "progress": 0,
                "estimatedTime": estimated_time,
                "dictionarySize": len(final_list),
                "method": "optimized_dictionary",
            },
        }
        self._emit_progress(progress_callback, "PROGRESS", result["details"])

        for i, pwd in enumerate(final_list, start=1):
            if i % 100 == 0 or i == total:
                progress = int((i / total) * 95)
                self.update_progress(progress, estimated_time, result["details"], progress_callback)

            if self._check_password(essid_safe, bssid, pwd):
                return self._finish(
                    result,
                    True,
                    "WEAK_PASSWORD",
                    pwd,
                    f"Обнаружен слабый пароль: {pwd}",
                    started_at,
                )

        if self._is_wps_vulnerable(bssid):
            return self._finish(
                result,
                True,
                "WPS_VULNERABLE",
                None,
                "Обнаружен риск WPS по OUI (рекомендуется отключить WPS).",
                started_at,
            )

        return self._finish(
            result,
            False,
            None,
            None,
            "Сеть не имеет слабых паролей в проверенных словарях.",
            started_at,
        )

    def _finish(
        self,
        result: Dict[str, Any],
        is_vulnerable: bool,
        vulnerability_type: Optional[str],
        password: Optional[str],
        message: str,
        started_at: float,
    ) -> Dict[str, Any]:
        result["is_vulnerable"] = is_vulnerable
        result["vulnerability_type"] = vulnerability_type
        result["password"] = password
        result["details"]["status"] = "completed"
        result["details"]["message"] = message
        result["details"]["progress"] = 100
        result["details"]["executionTime"] = round(time.time() - started_at, 3)
        return result

    def update_progress(
        self,
        progress: int,
        estimated_time: int,
        details: Dict[str, Any],
        progress_callback: ProgressCallback,
    ) -> None:
        details["progress"] = max(0, min(100, progress))
        details["estimatedTime"] = max(0, estimated_time)
        self._emit_progress(progress_callback, "PROGRESS", details)

    def _emit_progress(self, callback: ProgressCallback, state: str, meta: Dict[str, Any]) -> None:
        if callback is None:
            return
        try:
            callback(state=state, meta=meta)
        except Exception:
            logger.debug("Failed to emit task progress", exc_info=True)

    def _load_dictionary(self) -> list[str]:
        optimizer = DictionaryOptimizer(wordlists_path=str(Path(__file__).parent / "wordlists"))
        freq = FrequencyAnalyzer()
        pcfg = PCFGGenerator()

        optimized = optimizer.load_optimized_dictionary(top_n=1000)
        wifi_specific = optimizer.get_wifi_specific_dictionary()
        seeds = self.REGION_PASSWORD_SEEDS.get(self.region, [])

        manufacturer_words: list[str] = []
        manufacturers_path = Path(__file__).parent / "wordlists" / "manufacturers.txt"
        if manufacturers_path.exists():
            manufacturer_words = self._read_wordlist(manufacturers_path)

        pcfg_candidates = pcfg.generate([*seeds, *manufacturer_words], limit=500)

        merged = [*wifi_specific, *optimized, *pcfg_candidates, *seeds]
        merged = list(dict.fromkeys(merged))

        # Frequency ranking for practical top candidates.
        ranked = freq.zipf_ranked(merged, n=1000)
        if not ranked:
            ranked = list(self.DEFAULT_PASSWORDS)

        logger.info("Prepared %s audit candidates for region=%s", len(ranked), self.region)
        return ranked[:1000]

    def _read_wordlist(self, path: Path) -> list[str]:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                return [line.strip() for line in handle if line.strip()][:1000]
        except Exception:
            logger.warning("Unable to read wordlist %s", path, exc_info=True)
            return []

    def _estimate_time_seconds(self, dictionary_size: int) -> int:
        # Простая модель: ~0.08 сек на попытку + накладные расходы.
        return max(15, int(dictionary_size * 0.08) + 5)

    def _check_password(self, essid: str, bssid: str, password: str) -> bool:
        # Симуляция в рамках легального аудита.
        return "test" in essid.lower() and password == "password"

    def _check_wps_pin(self, essid: str, bssid: str, pin: str) -> bool:
        # Симуляция — внешние инструменты не запускаются здесь.
        return False

    def _is_wps_vulnerable(self, bssid: str) -> bool:
        oui = bssid.replace(":", "").upper()[:6]
        vulnerable_ouis = {"001122", "334455", "667788"}
        return oui in vulnerable_ouis
