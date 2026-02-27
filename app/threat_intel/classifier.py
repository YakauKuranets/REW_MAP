# -*- coding: utf-8 -*-
"""
Модуль классификации утечек данных и оценки критичности.
"""

import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class LeakClassifier:
    """Классифицирует утечки данных по типу и критичности."""

    LEAK_TYPES = [
        'credentials',
        'financial',
        'personal',
        'corporate',
        'source_code',
        'other',
    ]

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.classifier = None
        self.is_trained = False

    def classify(self, content: str, title: Optional[str] = None) -> Dict:
        text = f"{title or ''} {content or ''}"

        result = {
            'leak_type': 'unknown',
            'confidence': 0.0,
            'risk_score': 0,
            'indicators': {},
        }

        type_scores = self._keyword_classify(text)
        if type_scores:
            best_type = max(type_scores, key=type_scores.get)
            result['leak_type'] = best_type
            result['confidence'] = min(1.0, type_scores[best_type] / 100)

        result['risk_score'] = self._calculate_risk_score(text, result['leak_type'])
        result['indicators'] = {
            'has_emails': '@' in text,
            'has_passwords': bool(re.search(r'password[\s:=]+', text, re.I)),
            'has_credit_cards': bool(re.search(r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}', text)),
            'has_api_keys': bool(re.search(r'api[_-]?key', text, re.I)),
        }
        return result

    def _keyword_classify(self, text: str) -> Dict[str, float]:
        text_lower = text.lower()
        scores = {leak_type: 0 for leak_type in self.LEAK_TYPES}
        keywords = {
            'credentials': ['password', 'username', 'login', 'email', '@'],
            'financial': ['credit card', 'visa', 'mastercard', 'bank account', 'cvv'],
            'personal': ['passport', 'ssn', 'social security', 'address', 'phone'],
            'corporate': ['confidential', 'internal use', 'company', 'employee', 'salary'],
            'source_code': ['function', 'class', 'var', 'int main', '#include', 'import'],
        }
        for leak_type, words in keywords.items():
            for word in words:
                if word in text_lower:
                    scores[leak_type] += 10
        return scores

    def _calculate_risk_score(self, text: str, leak_type: str) -> int:
        score = 0
        type_risk = {
            'credentials': 70,
            'financial': 90,
            'personal': 60,
            'corporate': 50,
            'source_code': 40,
            'unknown': 30,
        }
        score += type_risk.get(leak_type, 30)
        if '@' in text and re.search(r'password', text, re.I):
            score += 20
        if re.search(r'\d{16}', text):
            score += 25
        if 'confidential' in text.lower() or 'secret' in text.lower():
            score += 15
        return min(score, 100)
