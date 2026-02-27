"""
Маршруты для установки роли и входа администратора.

Используются cookie‑сессии для хранения роли пользователя
(admin или guest). Права администратора проверяются в
helpers.require_admin().
"""

from datetime import datetime, timedelta

from flask import Response, abort, jsonify, request, session, current_app
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required

from ..audit.logger import log_admin_action
from ..security.rate_limit import check_rate_limit
from werkzeug.security import check_password_hash
from ..services.permissions_service import verify_admin_credentials
from ..extensions import db

from . import bp
from .models import ApiKey, User
from .utils import create_access_token as create_session_access_token, generate_api_key
from app.config import Config


@bp.post('/setrole/<role>')
def set_role(role: str) -> Response:
    """
    Установить роль пользователя.

    Гостевой режим отключён: переключение роли через этот роут запрещено.
    Роль 'admin' выставляется исключительно через /login.
    """
    abort(404)



@bp.post('/login')
def login() -> Response:
    """
    Вход администратора.

    Клиент отправляет JSON с полями 'username' и 'password'.

    Логика проверки:

    1) Сначала пытаемся найти администратора в таблице AdminUser
       (permissions_service.verify_admin_credentials).
    2) Если не нашли — используем legacy‑путь: сравнение с
       ADMIN_USERNAME / ADMIN_PASSWORD_HASH из конфигурации.

    При успешной проверке в сессии выставляются:

    - session['role'] = 'admin' (для совместимости со старым кодом);
    - session['admin_username'] = <username>;
    - session['admin_level'] = <role из AdminUser, если есть>;
    - session['username'] = <username> (как и раньше).
    """

    # --- Rate limit ---
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        limit = int(current_app.config.get("RATE_LIMIT_LOGIN_PER_MINUTE", 10))
        ok, info = check_rate_limit(bucket="login", ident=ip, limit=limit, window_seconds=60)
        if not ok:
            return jsonify(error="rate_limited", limit=info.limit, remaining=info.remaining, reset_in=info.reset_in), 429
    except Exception:
        # Никогда не ломаем логин из-за лимитера.
        pass

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    # 1) Пытаемся аутентифицировать по базе админов
    admin = verify_admin_credentials(username, password)
    if admin is not None:
        session['role'] = 'admin'
        session['is_admin'] = True
        session.permanent = True
        session['admin_username'] = admin.username
        session['admin_level'] = admin.role
        session['username'] = admin.username
        log_admin_action('auth.login', {'username': username})
        return jsonify({'status': 'ok', 'role': admin.role}), 200

    # 2) Легаси-путь: один админ из конфига
    stored_user = current_app.config.get('ADMIN_USERNAME')
    stored_hash = current_app.config.get('ADMIN_PASSWORD_HASH')
    if username == stored_user and stored_hash and check_password_hash(stored_hash, password):
        session['role'] = 'admin'
        session['is_admin'] = True
        session.permanent = True
        session['username'] = username
        session['admin_username'] = username
        session['admin_level'] = 'superadmin'
        log_admin_action('auth.login', {'username': username})
        return jsonify({'status': 'ok', 'role': 'superadmin'}), 200

    return jsonify({'error': 'Invalid credentials'}), 401


@bp.post('/logout')
def logout() -> Response:
    """Выйти из админской сессии (очистить cookie-сессию)."""
    log_admin_action('auth.logout')
    session.clear()
    return ('', 204)


@bp.get('/me')
def me() -> Response:
    """Текущая сессия (удобно для UI/диагностики)."""
    return jsonify({
        'is_admin': bool(session.get('is_admin')),
        'role': session.get('admin_level') if session.get('is_admin') else (session.get('role') or 'guest'),
        'username': session.get('admin_username') or session.get('username'),
    }), 200

@bp.post('/token')
def issue_token() -> Response:
    """Выдать access token для текущей админ-сессии."""
    if not session.get('is_admin'):
        return jsonify({'error': 'forbidden'}), 403
    username = session.get('admin_username') or session.get('username')
    role = session.get('admin_level') or 'admin'
    token = create_session_access_token(identity=username, role=role)
    return jsonify({'accessToken': token, 'tokenType': 'Bearer'}), 200


@bp.post('/api-keys')
def create_api_key_route() -> Response:
    """Создать API-ключ для мобильных клиентов (только админ)."""
    if not session.get('is_admin'):
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or 'mobile-client').strip()
    raw_key = generate_api_key()

    expires_days = int(current_app.config.get('API_KEY_EXPIRES_DAYS', 365))
    item = ApiKey(
        name=name,
        key=raw_key,
        permissions=(data.get('permissions') or 'diagnostics:read'),
        expires_at=ApiKey.default_expiry(expires_days),
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({
        'id': item.id,
        'name': item.name,
        'key': raw_key,
        'prefix': item.key[:8],
        'expiresAt': item.expires_at.isoformat(),
    }), 201


@bp.get('/api-keys')
def list_api_keys() -> Response:
    if not session.get('is_admin'):
        return jsonify({'error': 'forbidden'}), 403

    items = ApiKey.query.order_by(ApiKey.created_at.desc()).all()
    return jsonify([
        {
            'id': it.id,
            'name': it.name,
            'prefix': (it.key[:8] if it.key else ''),
            'isActive': it.is_active,
            'expiresAt': it.expires_at.isoformat(),
            'createdAt': it.created_at.isoformat(),
            'permissions': it.permissions,
            'lastUsed': it.last_used.isoformat() if it.last_used else None,
        }
        for it in items
    ]), 200


@bp.post('/auth/login')
def auth_login() -> Response:
    """JWT-аутентификация пользователя и выдача access/refresh токенов."""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    if not user.is_active:
        return jsonify({'error': 'Account disabled'}), 403

    user.last_login = datetime.utcnow()
    db.session.commit()

    access_token = create_access_token(identity=str(user.id), additional_claims={'role': user.role})
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'bearer',
        'expires_in': int(Config.JWT_ACCESS_TOKEN_EXPIRES.total_seconds()),
    }), 200


@bp.post('/auth/refresh')
@jwt_required(refresh=True)
def auth_refresh() -> Response:
    """Обновление access-токена по refresh-токену."""
    current_user_id = get_jwt_identity()
    token = create_access_token(identity=current_user_id)
    return jsonify({'access_token': token, 'token_type': 'bearer'}), 200


@bp.post('/auth/keys')
@jwt_required()
def auth_create_api_key() -> Response:
    """Создание API-ключа (только admin)."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    if not user or user.role != 'admin':
        return jsonify({'error': 'Admin privileges required'}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or 'Unnamed client').strip()
    expires_in_days = int(data.get('expires_in_days') or Config.API_KEY_EXPIRES_DAYS)

    api_key = ApiKey(
        key=ApiKey.generate_key(),
        name=name,
        user_id=user.id,
        permissions=(data.get('permissions') or 'diagnostics:read'),
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        is_active=True,
    )
    db.session.add(api_key)
    db.session.commit()

    return jsonify({
        'key': api_key.key,
        'name': api_key.name,
        'expires_at': api_key.expires_at.isoformat() if api_key.expires_at else None,
    }), 201


@bp.get('/auth/keys')
@jwt_required()
def auth_list_api_keys() -> Response:
    """Список API-ключей: admin видит все, остальные — только свои."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    keys = ApiKey.query.all() if user.role == 'admin' else ApiKey.query.filter_by(user_id=user.id).all()
    return jsonify([
        {
            'id': k.id,
            'name': k.name,
            'key_preview': (k.key[:8] + '...') if k.key else None,
            'expires_at': k.expires_at.isoformat() if k.expires_at else None,
            'last_used': k.last_used.isoformat() if k.last_used else None,
            'is_active': k.is_active,
            'permissions': k.permissions,
        }
        for k in keys
    ]), 200


@bp.post('/auth/keys/<int:key_id>/revoke')
@jwt_required()
def auth_revoke_api_key(key_id: int) -> Response:
    """Отзыв API-ключа."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    key = ApiKey.query.get_or_404(key_id)
    if key.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403

    key.is_active = False
    db.session.commit()
    return jsonify({'message': 'Key revoked'}), 200
