"""REST‑маршруты для управления администраторами (AdminUser).

Все маршруты требуют прав супер‑админа.
"""

from __future__ import annotations

from typing import Any, Dict, List

from compat_flask import jsonify, request

from . import bp
from ..extensions import db
from ..helpers import require_admin
from ..models import AdminUser, Zone
from compat_werkzeug_security import generate_password_hash


def _admin_to_dict(admin: AdminUser) -> Dict[str, Any]:
    return admin.to_dict()


@bp.get("/")
def list_admins():
    """Список администраторов (только для superadmin)."""
    require_admin(min_role="superadmin")
    admins = AdminUser.query.order_by(AdminUser.username.asc()).all()
    return jsonify([_admin_to_dict(a) for a in admins])


@bp.post("/")
def create_admin():
    """Создать нового администратора (только superadmin).

    Ожидаемый JSON:

    {
      "username": "name",
      "password": "plain-text",
      "role": "viewer|editor|superadmin",
      "zones": [1, 2, 3]  # опционально, id зон
    }
    """
    require_admin(min_role="superadmin")
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    role = (data.get("role") or "editor").strip() or "editor"
    zones_ids = data.get("zones") or []

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    if AdminUser.query.filter_by(username=username).first():
        return jsonify({"error": "username already exists"}), 400

    password_hash = generate_password_hash(password)

    admin = AdminUser(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=True,
    )

    if zones_ids:
        zones = Zone.query.filter(Zone.id.in_(zones_ids)).all()
        admin.zones = zones

    db.session.add(admin)
    db.session.commit()
    return jsonify(_admin_to_dict(admin)), 201


@bp.put("/<int:admin_id>")
@bp.patch("/<int:admin_id>")
def update_admin(admin_id: int):
    """Обновить администратора (роль/активность/зоны/пароль)."""
    require_admin(min_role="superadmin")
    admin = AdminUser.query.get(admin_id)
    if not admin:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or {}

    if "role" in data:
        role = (data.get("role") or "").strip()
        if role:
            admin.role = role

    if "is_active" in data:
        admin.is_active = bool(data.get("is_active"))

    if "password" in data:
        password = (data.get("password") or "").strip()
        if password:
            admin.password_hash = generate_password_hash(password)

    if "zones" in data:
        zones_ids = data.get("zones") or []
        zones = Zone.query.filter(Zone.id.in_(zones_ids)).all() if zones_ids else []
        admin.zones = zones

    db.session.commit()
    return jsonify(_admin_to_dict(admin)), 200


@bp.delete("/<int:admin_id>")
def delete_admin(admin_id: int):
    """Удалить администратора (hard delete) — только superadmin.

    При желании в будущем можно заменить на мягкое удаление
    (is_active = False), но сейчас реализован именно hard delete.
    """
    require_admin(min_role="superadmin")
    admin = AdminUser.query.get(admin_id)
    if not admin:
        return jsonify({"error": "not found"}), 404

    db.session.delete(admin)
    db.session.commit()
    return jsonify({"status": "ok"}), 200
