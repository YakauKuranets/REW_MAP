"""Flask application factory for MAP project."""

from __future__ import annotations

import os

from flask import Flask, jsonify, redirect, request

from .config import Config
from .extensions import db, init_extensions


def _register_blueprints(app: Flask) -> None:
    """Register all API blueprints used by the project."""
    from .addresses import bp as addresses_bp
    from .admin import bp as admin_bp
    from .admin_users import bp as admin_users_bp
    from .alerting import bp as alerting_bp
    from .analytics import bp as analytics_bp
    from .audit.routes import bp as audit_bp
    from .auth import bp as auth_bp
    from .bot import bp as bot_bp
    from .chat import bp as chat_bp
    from .duty import bp as duty_bp
    from .event_chat import bp as event_chat_bp
    from .general import bp as general_bp
    from .handshake import bp as handshake_bp
    from .geocode import bp as geocode_bp
    from .incidents import bp as incidents_bp
    from .maintenance import bp as maintenance_bp
    from .notifications import bp as notifications_bp
    from .objects import bp as objects_bp
    from .offline import bp as offline_bp
    from .pending import bp as pending_bp
    from .realtime import bp as realtime_bp
    from .requests import bp as requests_bp
    from .service_access import bp as service_access_bp
    from .system import bp as system_bp
    from .siem import bp as siem_bp
    from .terminals import bp as terminals_bp
    from .tracker import bp as tracker_bp
    from .threat_intel import bp as threat_intel_bp
    from .video import bp as video_bp
    from .websocket import ws_bp, sock
    from .wordlists import wordlists_bp
    from .diagnostics import bp as diagnostics_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(bot_bp, url_prefix="/api/bot")

    app.register_blueprint(addresses_bp, url_prefix="/api")
    app.register_blueprint(general_bp, url_prefix="/api")
    app.register_blueprint(geocode_bp, url_prefix="/api")
    app.register_blueprint(objects_bp, url_prefix="/api")
    app.register_blueprint(offline_bp, url_prefix="/api/offline")
    app.register_blueprint(pending_bp, url_prefix="/api/pending")
    app.register_blueprint(requests_bp, url_prefix="/api/requests")

    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    # Backward-compatible aliases used by older clients/tests.
    app.register_blueprint(admin_bp, url_prefix="/admin", name="admin_legacy")

    app.register_blueprint(admin_users_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(alerting_bp)
    app.register_blueprint(audit_bp, url_prefix="/api/audit")
    app.register_blueprint(chat_bp)
    app.register_blueprint(event_chat_bp)
    app.register_blueprint(incidents_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(realtime_bp)
    app.register_blueprint(handshake_bp)

    app.register_blueprint(duty_bp)
    app.register_blueprint(service_access_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(siem_bp, url_prefix="/api")
    app.register_blueprint(terminals_bp)
    app.register_blueprint(tracker_bp)
    app.register_blueprint(threat_intel_bp, url_prefix="/api")
    app.register_blueprint(video_bp)
    app.register_blueprint(wordlists_bp)
    app.register_blueprint(diagnostics_bp, url_prefix="/api")
    sock.init_app(app)
    app.register_blueprint(ws_bp)


def _register_common_routes(app: Flask) -> None:
    @app.get("/")
    def root_redirect():
        # Если пользователь авторизован — в командный центр,
        # иначе — на основную карту (содержит форму входа).
        from flask import session as _session
        if _session.get('is_admin'):
            return redirect("/admin/panel", code=302)
        return redirect("/admin/panel", code=302)  # панель сама перенаправит на логин через 403→login

    @app.get("/health")
    def health():
        return ("", 204)

    @app.get("/ready")
    def ready():
        return jsonify(status="ok"), 200

    @app.get(app.config.get("METRICS_PATH", "/metrics"))
    def metrics():
        if not app.config.get("ENABLE_METRICS", False):
            return jsonify(error="metrics_disabled"), 404

        allow_public = app.config.get("METRICS_ALLOW_PUBLIC", False)
        api_key = (app.config.get("METRICS_API_KEY") or "").strip()

        if not allow_public and request.remote_addr not in {"127.0.0.1", "::1", None}:
            if not api_key or request.headers.get("X-API-KEY") != api_key:
                return jsonify(error="forbidden"), 403

        return jsonify(status="ok"), 200


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def _forbidden(_err):
        if request.path.startswith("/api/"):
            return jsonify(error="forbidden"), 403
        return redirect("/login", code=302)


def _apply_security_headers(app: Flask) -> None:
    @app.after_request
    def _set_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp


def _register_cli(app: Flask) -> None:
    from .commands import create_admin, update_wordlists_command

    app.cli.add_command(create_admin)
    app.cli.add_command(update_wordlists_command)


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
        template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    )
    app.config.from_object(config_class)

    init_extensions(app)

    with app.app_context():
        from . import models  # noqa: F401
        from .vulnerabilities import models as vulnerability_models  # noqa: F401
        from .wordlists import models as wordlist_models  # noqa: F401
        from .diagnostics import models as diagnostics_models  # noqa: F401
        from .alerting import models as alerting_models  # noqa: F401
        from .darknet import models as darknet_models  # noqa: F401
        from .siem import models as siem_models  # noqa: F401
        db.create_all()

    os.makedirs(app.config.get("UPLOAD_FOLDER", "uploads"), exist_ok=True)

    _register_blueprints(app)
    _register_cli(app)
    _register_common_routes(app)
    _register_error_handlers(app)
    _apply_security_headers(app)
    return app
