# -*- coding: utf-8 -*-
"""
Модуль извлечения секретов из текстовых данных.
Комбинирует regex-правила для структурированных ключей и эвристику для паролей.
"""

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SecretExtractor:
    """Извлекает пароли, API-ключи, токены и другие секреты из текста."""

    def __init__(self, model_path: Optional[str] = None):
        self.regex_patterns = {
            'aws_key': r'AKIA[0-9A-Z]{16}',
            'jwt': r'eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*',
            'github_token': r'gh[ps]_[a-zA-Z0-9]{36}',
            'slack_token': r'xox[baprs]-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}',
            'ssh_key': r'-----BEGIN (?:RSA|DSA|EC|OPENSSH) PRIVATE KEY-----',
            'api_key': r'(?i)(api[_-]?key|apikey|secret)[\s:=]+[A-Za-z0-9_\-]{16,64}',
            'password_field': r'(?i)(password|passwd|pwd)[\s:=]+([^\s]{8,})',
            'email_pass': r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[\s:;]+([^\s]{6,})',
        }
        self.model_path = model_path
        self.use_ml = False

    def extract_all(self, text: str) -> List[Dict]:
        secrets = []
        secrets.extend(self._extract_regex(text or ""))
        return secrets

    def _extract_regex(self, text: str) -> List[Dict]:
        results = []
        for secret_type, pattern in self.regex_patterns.items():
            for match in re.finditer(pattern, text, re.MULTILINE):
                secret = {
                    'type': secret_type,
                    'value': match.group(),
                    'position': match.span(),
                    'context': text[max(0, match.start()-50):min(len(text), match.end()+50)],
                    'method': 'regex',
                }
                if secret_type == 'email_pass':
                    secret['email'] = match.group(1).strip()
                    secret['password'] = match.group(2).strip()
                    secret['domain'] = secret['email'].split('@', 1)[-1].lower() if '@' in secret['email'] else None
                    secret['type'] = 'credential'
                elif secret_type == 'password_field':
                    secret['password'] = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else match.group()
                    secret['type'] = 'password'
                results.append(secret)
        return results

    def validate_with_llm(self, candidates: List[Dict], _text: str) -> List[Dict]:
        validated = []
        for candidate in candidates:
            if candidate.get('value'):
                validated.append(candidate)
        return validated
