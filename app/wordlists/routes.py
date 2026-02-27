import os

from compat_flask import Blueprint, jsonify, send_file

from app.auth.decorators import jwt_or_api_required
from app.wordlists.models import Wordlist

wordlists_bp = Blueprint("wordlists", __name__, url_prefix="/wordlists")


@wordlists_bp.route("/version")
@jwt_or_api_required
def get_version():
    """Возвращает информацию о текущей версии словаря."""
    active = Wordlist.query.filter_by(is_active=True).first()
    if not active:
        return jsonify({"error": "No active wordlist"}), 404

    updated = active.updated_at.isoformat() if active.updated_at else active.created_at.isoformat()
    return jsonify(
        {
            "name": active.name,
            "version": active.version,
            "size": active.size,
            "hash": active.hash,
            "updated": updated,
        }
    )


@wordlists_bp.route("/download")
@jwt_or_api_required
def download_wordlist():
    """Скачивает активный словарь (только для авторизованных клиентов)."""
    active = Wordlist.query.filter_by(is_active=True).first()
    if not active or not active.file_path or not os.path.exists(active.file_path):
        return jsonify({"error": "Wordlist not found"}), 404

    return send_file(
        active.file_path,
        as_attachment=True,
        download_name=f"{active.name}_v{active.version}.txt",
        mimetype="text/plain",
    )
