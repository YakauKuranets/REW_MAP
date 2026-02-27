"""Admin audit logging helpers (best-effort) with Zero-Trust Blockchain-like Ledger."""

from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, Optional, Tuple

from compat_flask import request, session

from ..extensions import db
from ..models import AdminAuditLog
from ..helpers import get_current_admin


def generate_hash(data_dict: dict, prev_hash: str) -> str:
    """Генерирует SHA-256 хеш на основе данных записи и предыдущего хеша."""
    # Сортируем ключи, чтобы JSON всегда собирался одинаково
    data_string = json.dumps(data_dict, sort_keys=True, ensure_ascii=False)
    raw_string = f"{prev_hash}|{data_string}"
    return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()


def log_admin_action(action: str, payload: Optional[Dict[str, Any]] = None) -> None:
    """Записать аудит админского действия (с криптографической сшивкой).

    Best-effort: не должен ломать основную логику, поэтому ошибки подавляются.
    Zero-Trust: Каждая запись хешируется вместе с хешем предыдущей записи.
    """
    try:
        admin = get_current_admin()
        actor = None
        role = None
        if admin:
            actor = getattr(admin, 'username', None) or getattr(admin, 'login', None)
            role = getattr(admin, 'role', None) or getattr(admin, 'level', None)
        actor = actor or session.get('admin_username') or session.get('username')
        role = role or session.get('admin_level') or session.get('role')

        # IP: учитываем reverse-proxy
        ip = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip() or request.remote_addr

        # --- 🛡️ НАЧАЛО БЛОКА ZERO-TRUST ---
        # 1. Получаем хеш последней записи
        last_log = AdminAuditLog.query.order_by(AdminAuditLog.id.desc()).first()
        prev_hash = "GENESIS_BLOCK_0000000000000000"

        if last_log and last_log.payload_json:
            try:
                last_payload = json.loads(last_log.payload_json)
                prev_hash = last_payload.get('_crypto_signature', prev_hash)
            except Exception:
                pass

        # 2. Формируем данные для хеширования
        data_to_hash = {
            "actor": str(actor),
            "role": str(role),
            "ip": str(ip),
            "method": str(request.method),
            "path": str(request.path),
            "action": str(action),
            "payload": payload or {}
        }

        # 3. Вычисляем криптографическую подпись этой записи
        signature = generate_hash(data_to_hash, prev_hash)

        # 4. Внедряем подпись и ссылку на предыдущий блок в payload_json
        final_payload = dict(payload) if payload else {}
        final_payload['_crypto_signature'] = signature
        final_payload['_prev_hash'] = prev_hash
        # --- 🛡️ КОНЕЦ БЛОКА ZERO-TRUST ---

        row = AdminAuditLog(
            actor=actor,
            role=role,
            ip=ip,
            method=request.method,
            path=request.path,
            action=action,
            payload_json=json.dumps(final_payload, ensure_ascii=False),
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def verify_ledger_integrity() -> Tuple[bool, str]:
    """
    Проверяет всю базу логов на предмет скрытых изменений.
    Выявляет, если хакер удалил строку из БД или изменил её вручную.
    """
    try:
        logs = AdminAuditLog.query.order_by(AdminAuditLog.id.asc()).all()
        if not logs:
            return True, "Леджер пуст. Все в порядке."

        prev_hash = "GENESIS_BLOCK_0000000000000000"

        for log in logs:
            payload_dict = {}
            if log.payload_json:
                try:
                    payload_dict = json.loads(log.payload_json)
                except Exception:
                    pass

            stored_signature = payload_dict.get('_crypto_signature')
            stored_prev_hash = payload_dict.get('_prev_hash', prev_hash)

            # 1. Проверяем не порвана ли цепочка (не удалили ли строку)
            if stored_prev_hash != prev_hash:
                return False, f"🚨 Нарушение цепочки на ID {log.id}! Ожидался: {prev_hash}, найден: {stored_prev_hash}"

            # 2. Проверяем, не изменили ли сами данные в строке
            clean_payload = {k: v for k, v in payload_dict.items() if k not in ['_crypto_signature', '_prev_hash']}

            data_to_hash = {
                "actor": str(log.actor),
                "role": str(log.role),
                "ip": str(log.ip),
                "method": str(log.method),
                "path": str(log.path),
                "action": str(log.action),
                "payload": clean_payload
            }

            calculated_signature = generate_hash(data_to_hash, prev_hash)

            if calculated_signature != stored_signature:
                return False, f"🚨 Данные подменены на ID {log.id}! Подпись не совпадает с содержимым."

            prev_hash = stored_signature

        return True, "✅ Леджер абсолютно цел. Изменений 'задним числом' не обнаружено."
    except Exception as e:
        return False, f"Ошибка при проверке леджера: {e}"