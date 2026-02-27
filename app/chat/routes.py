"""Маршруты для работы с чатом.

API поддерживает следующие операции:

- ``GET /api/chat/conversations`` — список разговоров (уникальные user_id)
  с последним сообщением, статусом и счётчиками непрочитанного.
- ``GET /api/chat/<user_id>`` — полная история переписки с одним
  пользователем, упорядоченная по времени.
- ``POST /api/chat/<user_id>`` — отправить сообщение от администратора или
  пользователя.
- ``POST /api/chat/<user_id>/status`` — сменить статус диалога
  (new / in_progress / closed).
- ``POST /api/chat/<user_id>/read`` — отметить диалог как прочитанный
  администратором.

Вся тяжёлая бизнес‑логика вынесена в :mod:`app.services.chat_service`.
Здесь остаётся только HTTP‑обёртка: разбор параметров и формирование
ответа.
"""

from typing import Any, Dict

from compat_flask import jsonify, request, abort, current_app, session

from . import bp
from ..helpers import require_admin
from ..audit.logger import log_admin_action
from ..security.rate_limit import check_rate_limit
from ..services.chat_service import (
    list_conversations,
    get_history,
    get_history_paged,
    get_history_before,
    send_message,
    set_status,
    mark_read_by_admin,
    clear_history,
    delete_dialog,
    list_notify_targets,
    get_pending_admin_messages,
    ack_admin_notified,
    get_unread_for_user,
    mark_seen_admin,
)


def _require_bot_key() -> None:
    """Проверить X-API-KEY, если BOT_API_KEY задан.

    Если BOT_API_KEY пустой — оставляем легаси-поведение (разрешаем).
    """
    key = (current_app.config.get("BOT_API_KEY") or "").strip()
    if not key:
        return
    got = (request.headers.get("X-API-KEY") or "").strip()
    if got != key:
        abort(403)


def _rate_limit_chat() -> None:
    """Мягкий лимит на чат-запросы (чтобы не забили сервер)."""
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        limit = int(current_app.config.get("RATE_LIMIT_CHAT_PER_MINUTE", 120))
        ok, info = check_rate_limit(bucket="chat", ident=ip, limit=limit, window_seconds=60)
        if not ok:
            abort(429)
    except Exception:
        pass

@bp.get("/conversations")
def api_list_conversations():
    require_admin(min_role="viewer")
    """Вернуть список диалогов.

    Поддерживает опциональный фильтр по статусу:

        GET /api/chat/conversations?status=new

    Возвращает JSON‑массив словарей.
    """
    status = request.args.get("status")
    limit = request.args.get("limit", 200)
    offset = request.args.get("offset", 0)
    items = list_conversations(status=status, limit=limit, offset=offset)
    return jsonify(items)


@bp.get("/<user_id>")
def api_get_history(user_id: str):
    require_admin(min_role="viewer")
    """Вернуть историю переписки с указанным пользователем.

    Параметры (опционально):
      - limit (default 500, max 5000)
      - offset (default 0) — используется только если tail=0
      - tail=1|0 (по умолчанию 1, если limit/offset не заданы)

    Дополнительно (для infinite-scroll вверх в UI):
      - before_id=<int> : вернуть сообщения, которые *старше* указанного сообщения

    По умолчанию все сообщения пользователя считаются прочитанными
    администратором (сбрасывается счётчик непрочитанных).
    """

    # infinite-scroll: старше указанного сообщения
    if "before_id" in request.args:
        try:
            before_id = int(request.args.get("before_id") or "0")
        except Exception:
            before_id = 0
        limit = request.args.get("limit", 200)
        history = get_history_before(
            user_id=str(user_id),
            before_id=before_id,
            limit=limit,
            mark_as_read=False,
        )
        return jsonify(history)

    # backward-friendly: если клиент не передал пагинацию — отдаём последние N
    has_paging = ("limit" in request.args) or ("offset" in request.args) or ("tail" in request.args)
    if has_paging:
        limit = request.args.get("limit", 500)
        offset = request.args.get("offset", 0)
        tail = str(request.args.get("tail", "0")).strip().lower() in ("1", "true", "yes")
        history = get_history_paged(
            user_id=str(user_id),
            limit=limit,
            offset=offset,
            tail=tail,
            mark_as_read=True,
        )
    else:
        history = get_history_paged(user_id=str(user_id), limit=500, offset=0, tail=True, mark_as_read=True)

    return jsonify(history)


@bp.post("/<user_id>")

def api_send_message(user_id: str):
    # admin -> editor, bot/user -> BOT_API_KEY
    if session.get("is_admin"):
        require_admin(min_role="editor")
    else:
        _require_bot_key()
    _rate_limit_chat()
    """Отправить сообщение пользователю или от пользователя.

    Ожидает JSON с полями:

    - ``text`` — текст сообщения (обязателен);
    - ``sender`` — ``'user'`` или ``'admin'`` (по умолчанию ``'admin'``).
    """
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    text = (payload.get("text") or "").strip()
    sender = (payload.get("sender") or "admin").strip() or "admin"

    # Профиль пользователя (приходит от Telegram-бота) — нужен для отображения ников
    profile: Dict[str, Any] = {}
    u = payload.get('user')
    if isinstance(u, dict):
        profile = u
    else:
        # поддержим плоский формат
        for k in ('username', 'first_name', 'last_name', 'display_name', 'tg_username', 'tg_first_name', 'tg_last_name'):
            if k in payload:
                profile[k] = payload.get(k)

    if not text:
        return jsonify({"error": "text is required"}), 400

    msg_dict = send_message(user_id=str(user_id), text=text, sender=sender, profile=profile or None)
    if session.get('is_admin'):
        log_admin_action('chat.send_message', {'user_id': str(user_id), 'sender': sender})
    return jsonify(msg_dict), 201


@bp.post("/<user_id>/status")
def api_set_status(user_id: str):
    require_admin(min_role="editor")
    """Сменить статус диалога (new / in_progress / closed)."""
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    status = (payload.get("status") or "").strip()

    if not status:
        return jsonify({"error": "status is required"}), 400

    try:
        dialog_dict = set_status(user_id=str(user_id), status=status)
        log_admin_action('chat.set_status', {'user_id': str(user_id), 'status': status})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(dialog_dict)




@bp.get("/notify_targets")
def api_notify_targets():
    _require_bot_key()
    """Список пользователей, которым нужно прислать уведомление (для Telegram-бота)."""
    try:
        limit = int(request.args.get("limit") or 200)
    except Exception:
        limit = 200
    items = list_notify_targets(limit=limit)
    return jsonify(items)


@bp.get("/<user_id>/pending_admin")
def api_pending_admin(user_id: str):
    _require_bot_key()
    """Вернуть новые сообщения от админа для уведомлений.

    Используется Telegram-ботом в polling режиме.
    """
    try:
        limit = int(request.args.get("limit") or 10)
    except Exception:
        limit = 10
    data = get_pending_admin_messages(user_id=str(user_id), limit=limit)
    return jsonify(data)


@bp.post("/<user_id>/ack_admin")
def api_ack_admin(user_id: str):
    _require_bot_key()
    """Подтвердить доставку уведомлений пользователю (cursor = id сообщения)."""
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    cursor = payload.get("cursor") or 0
    dialog = ack_admin_notified(user_id=str(user_id), cursor=cursor)
    return jsonify(dialog)

@bp.get("/<user_id>/unread_user")
def api_unread_user(user_id: str):
    _require_bot_key()
    """Сколько непрочитанных сообщений от админа у пользователя (для кнопки в боте)."""
    data = get_unread_for_user(user_id=str(user_id))
    return jsonify(data)


@bp.post("/<user_id>/seen_admin")
def api_seen_admin(user_id: str):
    _require_bot_key()
    """Пометить сообщения админа как просмотренные пользователем (cursor=id)."""
    payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    cursor = payload.get("cursor") or 0
    dialog = mark_seen_admin(user_id=str(user_id), cursor=cursor)
    return jsonify(dialog)


@bp.post("/<user_id>/read")
def api_mark_read(user_id: str):
    require_admin(min_role="editor")
    """Отметить сообщения пользователя как прочитанные администратором."""
    dialog_dict = mark_read_by_admin(user_id=str(user_id))
    log_admin_action('chat.read', {'user_id': str(user_id)})
    return jsonify(dialog_dict)


# Новая ручка: очистить историю переписки
@bp.delete("/<user_id>")
def api_clear_history(user_id: str):
    require_admin(min_role="editor")
    """Очистить все сообщения диалога с указанным пользователем.

    Возвращает количество удалённых сообщений и текущее состояние диалога.
    """
    result = clear_history(user_id=str(user_id))
    log_admin_action('chat.clear_history', {'user_id': str(user_id), 'deleted': int(result.get('deleted') or 0)})
    return jsonify(result)


@bp.delete("/<user_id>/dialog")
def api_delete_dialog(user_id: str):
    require_admin(min_role="editor")
    """Удалить диалог полностью (сообщения + запись диалога)."""
    result = delete_dialog(user_id=str(user_id))
    log_admin_action('chat.delete_dialog', {'user_id': str(user_id)})
    return jsonify(result)


