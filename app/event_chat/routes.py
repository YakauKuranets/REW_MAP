"""Маршруты для событийного чата (MVP).

Этот модуль содержит базовые HTTP‑эндпоинты для управления
каналами, отправки сообщений и чтения истории. Логика максимально
простая и является отправной точкой для дальнейшего развития.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, List

from flask import request, jsonify, abort, session, current_app

from ..helpers import require_admin
from ..extensions import db
from ..realtime.hub import broadcast_sync
from . import bp
from .models import Channel, Message, ChannelMember, PushToken
from werkzeug.utils import secure_filename
import os
import uuid
import json

# Импортируем rate-limiter, метрики и push
from .ratelimit import check_rate
from .metrics import inc
from .push import send_push


def _get_current_user() -> tuple[str, str]:
    """Определить отправителя (тип и id) из сессии или заголовков.

    Администраторы идентифицируются через cookie‑сессию
    (``session['is_admin']``); устройства передают ``X-Device-ID``.
    Возвращает `(sender_type, sender_id)`. Бросает 403, если
    идентификация не удалась.
    """
    # Admin session
    if session.get("is_admin"):
        sender_type = "admin"
        # Используем id или имя пользователя
        sender_id = str(session.get("admin_id") or session.get("username") or "admin")
        return sender_type, sender_id
    # Tracker by header (MVP)
    device_id = (request.headers.get("X-Device-ID") or "").strip()
    if device_id:
        return "tracker", device_id
    abort(403)



def _unread_count_for_member(channel_id: str, member_type: str, member_id: str, *, exclude_self: bool = True) -> int:
    """Подсчитать непрочитанные сообщения для участника канала.

    В MVP считаем непрочитанными сообщения, созданные после last_read_message_id/last_read_at.
    По умолчанию исключаем собственные сообщения участника.
    """
    q = Message.query.filter(Message.channel_id == channel_id)
    if exclude_self:
        q = q.filter(~((Message.sender_type == member_type) & (Message.sender_id == member_id)))

    cm = ChannelMember.query.filter_by(channel_id=channel_id, member_type=member_type, member_id=member_id).first()
    if cm and cm.last_read_message_id:
        ref = Message.query.filter_by(id=cm.last_read_message_id, channel_id=channel_id).first()
        if ref and ref.created_at:
            q = q.filter(Message.created_at > ref.created_at)
        elif cm.last_read_at:
            q = q.filter(Message.created_at > cm.last_read_at)
    elif cm and cm.last_read_at:
        q = q.filter(Message.created_at > cm.last_read_at)

    try:
        return int(q.count())
    except Exception:
        return 0


# Предопределённые шаблоны быстрых сообщений
TEMPLATES: List[Dict[str, str]] = [
    {"id": "arrived", "text": "Прибыл"},
    {"id": "need_help", "text": "Нужна помощь"},
    {"id": "bad_signal", "text": "Связь плохая"},
    {"id": "delivered", "text": "Доставил"},
]


@bp.post("/create_channel")
def api_create_channel():
    """Создать новый канал.

    Ожидает JSON:
      - ``type`` — ``shift``, ``incident`` или ``dm``;
      - ``shift_id`` или ``marker_id`` (опционально);
      - ``members`` — список участников вида {"member_type", "member_id"}
        (можно опустить в MVP).

    Возвращает ID созданного канала и его тип.
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    typ: str = str(payload.get("type") or "").strip()
    if not typ:
        return jsonify({"error": "type is required"}), 400
    shift_id: Optional[int] = payload.get("shift_id")
    marker_id: Optional[int] = payload.get("marker_id")
    channel = Channel(type=typ, shift_id=shift_id, marker_id=marker_id, created_at=datetime.utcnow())
    db.session.add(channel)
    db.session.commit()

    members = payload.get("members") or []
    for m in members:
        try:
            member_type = str(m.get("member_type")).strip()
            member_id = str(m.get("member_id")).strip()
        except Exception:
            continue
        if not member_type or not member_id:
            continue
        cm = ChannelMember(channel_id=channel.id, member_type=member_type, member_id=member_id)
        db.session.add(cm)
    if members:
        db.session.commit()

    return jsonify({"id": channel.id, "type": channel.type, "shift_id": channel.shift_id, "marker_id": channel.marker_id}), 201


@bp.post("/send")
def api_chat_send():
    """Отправить сообщение в существующий канал.

    Ожидает JSON с полями:
      - ``channel_id`` (обязателен);
      - ``text`` — текст сообщения (обязательно для ``kind=text``);
      - ``kind`` — тип сообщения (``text`` по умолчанию);
      - ``client_msg_id`` — клиентский идентификатор.

    Возвращает созданное сообщение.
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    channel_id: str = str(payload.get("channel_id") or "").strip()
    text: Optional[str] = payload.get("text")
    kind: str = str(payload.get("kind") or "text").strip()
    client_msg_id: Optional[str] = payload.get("client_msg_id")
    if not channel_id:
        return jsonify({"error": "channel_id is required"}), 400
    if kind == "text" and not text:
        return jsonify({"error": "text is required"}), 400
    channel = Channel.query.filter_by(id=channel_id).first()
    if not channel:
        return jsonify({"error": "channel not found"}), 404
    sender_type, sender_id = _get_current_user()

    # Применяем ограничение частоты отправки
    window_sec = float(current_app.config.get("CHAT2_SEND_RATE_WINDOW_SEC", 60.0))
    limit = int(current_app.config.get("CHAT2_SEND_RATE_LIMIT", 20))
    if not check_rate((sender_type, sender_id, "send"), window_sec, limit):
        inc("chat2_messages_failed_rate_limit_total")
        return jsonify({"error": "rate limit exceeded"}), 429

    # Idempotency (store-and-forward friendly): if client retries the same
    # message with the same client_msg_id, we return the previously created
    # message and do NOT broadcast again.
    if client_msg_id:
        try:
            existing = Message.query.filter_by(
                channel_id=channel.id,
                sender_type=sender_type,
                sender_id=sender_id,
                client_msg_id=client_msg_id,
            ).order_by(Message.created_at.desc()).first()
            if existing:
                return jsonify(existing.to_dict()), 200
        except Exception:
            current_app.logger.debug("Failed to check idempotency for chat2 send", exc_info=True)

    msg = Message(
        channel_id=channel.id,
        sender_type=sender_type,
        sender_id=sender_id,
        client_msg_id=client_msg_id,
        text=text,
        kind=kind,
        created_at=datetime.utcnow(),
    )
    db.session.add(msg)
    channel.last_message_at = msg.created_at
    db.session.commit()
    # Рассылаем событие в realtime-хаб. Клиенты сами фильтруют по channel_id.
    try:
        broadcast_sync("chat2_message", msg.to_dict())
    except Exception:
        current_app.logger.debug("Failed to broadcast chat2_message", exc_info=True)

    # Обновляем метрики
    inc("chat2_messages_sent_total")
    # Рассылаем push-уведомления участникам канала, кроме отправителя
    try:
        if current_app.config.get("CHAT2_PUSH_ENABLED"):
            member_pairs = [(m.member_type, m.member_id) for m in channel.members]
            tokens: List[str] = []
            for mtype, mid in member_pairs:
                if mtype == sender_type and mid == sender_id:
                    continue
                pts = PushToken.query.filter_by(member_type=mtype, member_id=mid).all()
                tokens.extend([pt.token for pt in pts if pt.token])
            tokens = list(dict.fromkeys(tokens))
            if tokens:
                title = current_app.config.get("CHAT2_PUSH_TITLE", "Новое сообщение")
                body = text or ""
                data = {
                    "channel_id": channel_id,
                    "message_id": msg.id,
                    "kind": kind,
                }
                res = send_push(title, body, tokens, data=data)
                if res.get("sent"):
                    inc("chat2_push_sent_total", res["sent"])
    except Exception:
        current_app.logger.debug("Failed to send push", exc_info=True)
    return jsonify(msg.to_dict()), 201


@bp.get("/history")
def api_chat_history():
    """Получить историю сообщений канала.

    Query‑параметры:
      - ``channel_id`` (обязателен);
      - ``limit`` (int) — сколько сообщений вернуть (по умолчанию 50);
      - ``before_id`` — ID сообщения; возвращаем записи, созданные
        строго до него.

    Возвращает массив сообщений в обратном хронологическом порядке (последние – первые).
    """
    channel_id: str = str(request.args.get("channel_id") or "").strip()
    if not channel_id:
        return jsonify({"error": "channel_id is required"}), 400
    try:
        limit = int(request.args.get("limit") or 50)
    except Exception:
        limit = 50
    before_id = request.args.get("before_id")
    q = Message.query.filter_by(channel_id=channel_id)
    if before_id:
        ref = Message.query.filter_by(id=before_id, channel_id=channel_id).first()
        if ref:
            q = q.filter(Message.created_at < ref.created_at)
    q = q.order_by(Message.created_at.desc()).limit(limit)
    msgs = [m.to_dict() for m in q]
    return jsonify(msgs)


@bp.get("/sync")
def api_chat_sync():
    """Синхронизировать пропущенные сообщения канала.

    Query‑параметры:
      - ``channel_id`` (обязателен);
      - ``after_id`` — ID последнего сообщения, которое видит клиент;
      - ``limit`` (int) — сколько сообщений вернуть (по умолчанию 200).

    Возвращает список сообщений, созданных после указанного ID, отсортированный
    по возрастанию времени (старые -> новые).
    """
    channel_id: str = str(request.args.get("channel_id") or "").strip()
    if not channel_id:
        return jsonify({"error": "channel_id is required"}), 400
    try:
        limit = int(request.args.get("limit") or 200)
    except Exception:
        limit = 200
    after_id = request.args.get("after_id")
    q = Message.query.filter_by(channel_id=channel_id)
    if after_id:
        ref = Message.query.filter_by(id=after_id, channel_id=channel_id).first()
        if ref:
            q = q.filter(Message.created_at > ref.created_at)
    q = q.order_by(Message.created_at.asc()).limit(limit)
    msgs = [m.to_dict() for m in q]
    return jsonify(msgs)


@bp.post("/read")
def api_chat_mark_read():
    """Отметить канал прочитанным до указанного сообщения.

    Ожидает JSON:
      - ``channel_id``;
      - ``last_read_message_id``.

    Сохраняет отметку в ``ChannelMember`` для текущего пользователя.
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    channel_id: str = str(payload.get("channel_id") or "").strip()
    last_id: str = str(payload.get("last_read_message_id") or "").strip()
    if not channel_id or not last_id:
        return jsonify({"error": "channel_id and last_read_message_id are required"}), 400
    channel = Channel.query.filter_by(id=channel_id).first()
    if not channel:
        return jsonify({"error": "channel not found"}), 404
    sender_type, sender_id = _get_current_user()
    cm = ChannelMember.query.filter_by(channel_id=channel_id, member_type=sender_type, member_id=sender_id).first()
    now = datetime.utcnow()
    if not cm:
        cm = ChannelMember(channel_id=channel_id, member_type=sender_type, member_id=sender_id, last_read_message_id=last_id, last_read_at=now)
        db.session.add(cm)
    else:
        cm.last_read_message_id = last_id
        cm.last_read_at = now
    db.session.commit()
    return jsonify({"status": "ok"})


@bp.post("/receipt")
def api_chat_receipt():
    """Принять подтверждение доставки или прочтения сообщения.

    Ожидает JSON с полями:
      - ``channel_id`` — идентификатор канала;
      - ``message_id`` — идентификатор сообщения;
      - ``type`` — ``delivered`` или ``read``.

    Увеличивает счётчик ``delivered_count`` или ``read_count`` в сообщении и
    рассылает событие ``chat2_receipt`` по WS. В ответ возвращает
    обновлённые значения счётчиков.
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    channel_id: str = str(payload.get("channel_id") or "").strip()
    message_id: str = str(payload.get("message_id") or "").strip()
    rec_type: str = str(payload.get("type") or "").strip().lower()
    if not channel_id or not message_id or not rec_type:
        return jsonify({"error": "channel_id, message_id and type are required"}), 400
    # Проверяем канал и сообщение
    channel = Channel.query.filter_by(id=channel_id).first()
    if not channel:
        return jsonify({"error": "channel not found"}), 404
    msg = Message.query.filter_by(id=message_id, channel_id=channel_id).first()
    if not msg:
        return jsonify({"error": "message not found"}), 404
    if rec_type not in ("delivered", "read"):
        return jsonify({"error": "type must be delivered or read"}), 400
    # Определяем отправителя (кто подтверждает)
    sender_type, sender_id = _get_current_user()
    # Обновляем счётчики
    updated = False
    if rec_type == "delivered":
        msg.delivered_count = (msg.delivered_count or 0) + 1
        updated = True
    elif rec_type == "read":
        msg.read_count = (msg.read_count or 0) + 1
        updated = True
    if updated:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "failed to update receipt"}), 500
        # Рассылаем событие квитанции
        event_data = {
            "channel_id": channel_id,
            "message_id": message_id,
            "type": rec_type,
            "who": {"type": sender_type, "id": sender_id},
            "delivered_count": msg.delivered_count,
            "read_count": msg.read_count,
        }
        try:
            broadcast_sync("chat2_receipt", event_data)
        except Exception:
            current_app.logger.debug("Failed to broadcast chat2_receipt", exc_info=True)
        return jsonify(event_data), 200
    # Не должно сюда дойти
    return jsonify({"error": "no update"}), 400


@bp.post("/upload_media")
def api_chat_upload_media():
    """Загрузить файл и создать сообщение с медиа.

    Ожидает form-data:
      - ``channel_id`` — идентификатор канала (обязателен);
      - ``file`` — загружаемый файл (обязателен);
      - ``text`` — подпись (optional).

    Сохраняет файл в ``UPLOAD_FOLDER/chat2``. Возвращает объект сообщения.
    """
    # Multipart form
    channel_id = str(request.form.get("channel_id") or "").strip()
    caption = request.form.get("text")
    client_msg_id = (request.form.get("client_msg_id") or "").strip() or None
    if not channel_id:
        return jsonify({"error": "channel_id is required"}), 400
    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "file must have a name"}), 400
    channel = Channel.query.filter_by(id=channel_id).first()
    if not channel:
        return jsonify({"error": "channel not found"}), 404
    sender_type, sender_id = _get_current_user()

    # Idempotency: if the client retries upload with the same client_msg_id,
    # return existing message and do not create duplicates.
    if client_msg_id:
        try:
            existing = Message.query.filter_by(
                channel_id=channel_id,
                sender_type=sender_type,
                sender_id=sender_id,
                client_msg_id=client_msg_id,
            ).order_by(Message.created_at.desc()).first()
            if existing:
                return jsonify(existing.to_dict()), 200
        except Exception:
            current_app.logger.debug("Failed to check idempotency for chat2 upload", exc_info=True)
    # Rate limit for uploads
    upload_window = float(current_app.config.get("CHAT2_UPLOAD_RATE_WINDOW_SEC", 60.0))
    upload_limit = int(current_app.config.get("CHAT2_UPLOAD_RATE_LIMIT", 5))
    if not check_rate((sender_type, sender_id, "upload"), upload_window, upload_limit):
        inc("chat2_messages_failed_rate_limit_total")
        return jsonify({"error": "rate limit exceeded"}), 429
    # Prepare upload directory
    upload_root = current_app.config.get("UPLOAD_FOLDER") or "uploads"
    subdir = os.path.join(upload_root, "chat2")
    os.makedirs(subdir, exist_ok=True)
    # Generate unique filename preserving extension
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(subdir, unique_name)
    # Save file
    file.save(filepath)
    # Gather meta
    media_key = os.path.relpath(filepath, upload_root).replace("\\", "/")
    mime = file.mimetype
    try:
        size = os.path.getsize(filepath)
    except Exception:
        size = None
    msg = Message(
        channel_id=channel_id,
        sender_type=sender_type,
        sender_id=sender_id,
        client_msg_id=client_msg_id,
        text=caption,
        kind="media",
        media_key=media_key,
        mime=mime,
        size=size,
        created_at=datetime.utcnow(),
    )
    db.session.add(msg)
    channel.last_message_at = msg.created_at
    db.session.commit()
    # Broadcast via WS
    try:
        broadcast_sync("chat2_message", msg.to_dict())
    except Exception:
        current_app.logger.debug("Failed to broadcast media message", exc_info=True)
    # Metrics
    inc("chat2_messages_sent_total")
    inc("chat2_media_uploaded_total")
    # Push notifications
    try:
        if current_app.config.get("CHAT2_PUSH_ENABLED"):
            member_pairs = [(m.member_type, m.member_id) for m in channel.members]
            tokens: List[str] = []
            for mtype, mid in member_pairs:
                if mtype == sender_type and mid == sender_id:
                    continue
                pts = PushToken.query.filter_by(member_type=mtype, member_id=mid).all()
                tokens.extend([pt.token for pt in pts if pt.token])
            tokens = list(dict.fromkeys(tokens))
            if tokens:
                title = current_app.config.get("CHAT2_PUSH_TITLE", "Новое медиа")
                body = caption or "(медиа)"
                data = {
                    "channel_id": channel_id,
                    "message_id": msg.id,
                    "kind": "media",
                }
                res = send_push(title, body, tokens, data=data)
                if res.get("sent"):
                    inc("chat2_push_sent_total", res["sent"])
    except Exception:
        current_app.logger.debug("Failed to send media push", exc_info=True)
    return jsonify(msg.to_dict()), 201


@bp.get("/search")
def api_chat_search():
    """Поиск по сообщениям в канале.

    Query‑параметры:
      - ``channel_id`` — обязательный идентификатор канала;
      - ``query`` — текст для поиска (обязателен);
      - ``limit`` — максимальное количество результатов (по умолчанию 50).

    Возвращает список сообщений, содержащих подстроку ``query`` в поле
    ``text``, отсортированный по возрастанию времени.
    """
    channel_id: str = str(request.args.get("channel_id") or "").strip()
    qtext: str = str(request.args.get("query") or "").strip()
    if not channel_id:
        return jsonify({"error": "channel_id is required"}), 400
    if not qtext:
        return jsonify({"error": "query is required"}), 400
    try:
        limit = int(request.args.get("limit") or 50)
    except Exception:
        limit = 50
    query = Message.query.filter_by(channel_id=channel_id)
    # Ищем только по тексту, игнорируя None
    query = query.filter(Message.text.ilike(f"%{qtext}%"))
    query = query.order_by(Message.created_at.asc()).limit(limit)
    results = [m.to_dict() for m in query]
    return jsonify(results)


@bp.get("/templates")
def api_chat_templates():
    """Список предустановленных шаблонов сообщений."""
    return jsonify(TEMPLATES)


@bp.post("/send_template")
def api_chat_send_template():
    """Отправить сообщение на основе шаблона.

    Ожидает JSON:
      - ``channel_id`` — идентификатор канала (обязателен);
      - ``template_id`` — ID шаблона (обязателен).
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    channel_id: str = str(payload.get("channel_id") or "").strip()
    template_id: str = str(payload.get("template_id") or "").strip()
    if not channel_id or not template_id:
        return jsonify({"error": "channel_id and template_id are required"}), 400
    channel = Channel.query.filter_by(id=channel_id).first()
    if not channel:
        return jsonify({"error": "channel not found"}), 404
    sender_type, sender_id = _get_current_user()
    # Rate limit
    window_sec = float(current_app.config.get("CHAT2_SEND_RATE_WINDOW_SEC", 60.0))
    limit = int(current_app.config.get("CHAT2_SEND_RATE_LIMIT", 20))
    if not check_rate((sender_type, sender_id, "send"), window_sec, limit):
        inc("chat2_messages_failed_rate_limit_total")
        return jsonify({"error": "rate limit exceeded"}), 429
    # Find template
    tmpl = next((t for t in TEMPLATES if str(t.get("id")) == template_id), None)
    if not tmpl:
        return jsonify({"error": "template not found"}), 404
    text = tmpl.get("text")
    meta = {"template_id": template_id}
    msg = Message(
        channel_id=channel_id,
        sender_type=sender_type,
        sender_id=sender_id,
        text=text,
        kind="template",
        meta_json=meta,
        created_at=datetime.utcnow(),
    )
    db.session.add(msg)
    channel.last_message_at = msg.created_at
    db.session.commit()
    # Broadcast
    try:
        broadcast_sync("chat2_message", msg.to_dict())
    except Exception:
        current_app.logger.debug("Failed to broadcast template message", exc_info=True)
    # Metrics
    inc("chat2_messages_sent_total")
    # Push
    try:
        if current_app.config.get("CHAT2_PUSH_ENABLED"):
            member_pairs = [(m.member_type, m.member_id) for m in channel.members]
            tokens: List[str] = []
            for mtype, mid in member_pairs:
                if mtype == sender_type and mid == sender_id:
                    continue
                pts = PushToken.query.filter_by(member_type=mtype, member_id=mid).all()
                tokens.extend([pt.token for pt in pts if pt.token])
            tokens = list(dict.fromkeys(tokens))
            if tokens:
                title = current_app.config.get("CHAT2_PUSH_TITLE", "Новый шаблон")
                body = text or ""
                data = {
                    "channel_id": channel_id,
                    "message_id": msg.id,
                    "kind": "template",
                    "template_id": template_id,
                }
                res = send_push(title, body, tokens, data=data)
                if res.get("sent"):
                    inc("chat2_push_sent_total", res["sent"])
    except Exception:
        current_app.logger.debug("Failed to send template push", exc_info=True)
    return jsonify(msg.to_dict()), 201


@bp.post("/push/register")
def api_chat_register_push():
    """Регистрация push‑токена для текущего пользователя.

    Ожидает JSON:
      - ``token`` — токен FCM/APNs (обязателен).
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    token: str = str(payload.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token is required"}), 400
    sender_type, sender_id = _get_current_user()
    existing = PushToken.query.filter_by(token=token).first()
    if existing:
        existing.member_type = sender_type
        existing.member_id = sender_id
        db.session.commit()
        return jsonify({"status": "updated", "id": existing.id})
    pt = PushToken(member_type=sender_type, member_id=sender_id, token=token, created_at=datetime.utcnow())
    db.session.add(pt)
    db.session.commit()
    return jsonify({"status": "registered", "id": pt.id}), 201


@bp.post("/push/test")
def api_chat_push_test():
    """Отправить тестовое push‑сообщение.

    Ожидает JSON:
      - ``token`` — (optional) конкретный токен для теста.
    """
    require_admin("viewer")
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    token = payload.get("token")
    tokens: List[str]
    if token:
        tokens = [str(token).strip()]
    else:
        tokens = [pt.token for pt in PushToken.query.all()]
    res = send_push("Test", "This is a test notification", tokens)
    if res.get("sent"):
        inc("chat2_push_sent_total", res["sent"])
    return jsonify({"sent": res.get("sent")}), 200


@bp.get("/channels")
def api_chat_channels():
    """Список каналов для администратора.

    Возвращает каналы с последним сообщением и количеством непрочитанных
    сообщений (для MVP непрочитанные оцениваются по ChannelMember).
    """
    require_admin("viewer")
    try:
        limit = int(request.args.get("limit") or 50)
    except Exception:
        limit = 50
    qs = Channel.query.order_by(Channel.last_message_at.desc().nullslast()).limit(limit)
    res: List[Dict[str, Any]] = []
    for ch in qs:
        last_msg = Message.query.filter_by(channel_id=ch.id).order_by(Message.created_at.desc()).first()
        if last_msg:
            preview = last_msg.text or (last_msg.kind or "")
        else:
            preview = None
        # Подсчёт непрочитанных для текущего пользователя (исключая его же сообщения)
        sender_type, sender_id = _get_current_user()
        unread = _unread_count_for_member(ch.id, sender_type, sender_id, exclude_self=True)
        res.append({
            "id": ch.id,
            "type": ch.type,
            "shift_id": ch.shift_id,
            "marker_id": ch.marker_id,
            "last_message_at": ch.last_message_at.isoformat() if ch.last_message_at else None,
            "preview": preview,
            "unread": unread,
        })
    return jsonify(res)



@bp.get("/unread_for_incidents")
def api_chat_unread_for_incidents():
    """Вернуть количество непрочитанных сообщений по списку инцидентов.

    Запрос: /api/chat2/unread_for_incidents?ids=1,2,3
    Ответ: {"1": 3, "2": 0}

    Важно: считаем непрочитанными только сообщения, отправленные НЕ текущим пользователем.
    """
    require_admin("viewer")

    ids_raw = str(request.args.get("ids") or "").strip()
    if not ids_raw:
        return jsonify({}), 200

    ids: List[int] = []
    for part in ids_raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except Exception:
            continue

    sender_type, sender_id = _get_current_user()
    if sender_type != "admin":
        abort(403)

    out: Dict[str, int] = {}
    if not ids:
        return jsonify(out), 200

    channels = Channel.query.filter(Channel.type == "incident", Channel.marker_id.in_(ids)).all()
    by_marker: Dict[int, Channel] = {int(ch.marker_id): ch for ch in channels if ch.marker_id is not None}

    for iid in ids:
        ch = by_marker.get(int(iid))
        if not ch:
            out[str(iid)] = 0
            continue
        out[str(iid)] = _unread_count_for_member(ch.id, sender_type, sender_id, exclude_self=True)

    return jsonify(out), 200


@bp.get("/unread_for_shifts")
def api_chat_unread_for_shifts():
    """Вернуть количество непрочитанных сообщений по списку смен.

    Запрос: /api/chat2/unread_for_shifts?ids=101,102
    Ответ: {"101": 1, "102": 0}
    """
    require_admin("viewer")

    ids_raw = str(request.args.get("ids") or "").strip()
    if not ids_raw:
        return jsonify({}), 200

    ids: List[int] = []
    for part in ids_raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except Exception:
            continue

    sender_type, sender_id = _get_current_user()
    if sender_type != "admin":
        abort(403)

    out: Dict[str, int] = {}
    if not ids:
        return jsonify(out), 200

    channels = Channel.query.filter(Channel.type == "shift", Channel.shift_id.in_(ids)).all()
    by_shift: Dict[int, Channel] = {int(ch.shift_id): ch for ch in channels if ch.shift_id is not None}

    for sid in ids:
        ch = by_shift.get(int(sid))
        if not ch:
            out[str(sid)] = 0
            continue
        out[str(sid)] = _unread_count_for_member(ch.id, sender_type, sender_id, exclude_self=True)

    return jsonify(out), 200


@bp.post("/ensure_shift_channel")
def api_chat_ensure_shift_channel():
    """Получить или создать канал для смены.

    Ожидает JSON:
      - ``shift_id`` — идентификатор смены (обязателен);
      - ``members`` — список участников {"member_type","member_id"} (optional).
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    shift_id = payload.get("shift_id")
    if not shift_id:
        return jsonify({"error": "shift_id is required"}), 400
    try:
        shift_id_int = int(shift_id)
    except Exception:
        return jsonify({"error": "shift_id must be int"}), 400
    ch = Channel.query.filter_by(type="shift", shift_id=shift_id_int).first()
    created = False
    if not ch:
        ch = Channel(type="shift", shift_id=shift_id_int, created_at=datetime.utcnow())
        db.session.add(ch)
        db.session.commit()
        created = True
    members = payload.get("members") or []
    for m in members:
        mt = str(m.get("member_type") or "").strip()
        mid = str(m.get("member_id") or "").strip()
        if not mt or not mid:
            continue
        exists = ChannelMember.query.filter_by(channel_id=ch.id, member_type=mt, member_id=mid).first()
        if not exists:
            cm = ChannelMember(channel_id=ch.id, member_type=mt, member_id=mid)
            db.session.add(cm)
    if members:
        db.session.commit()
    return jsonify({"id": ch.id, "created": created}), 200


@bp.post("/ensure_incident_channel")
def api_chat_ensure_incident_channel():
    """Получить или создать канал для инцидента.

    Ожидает JSON:
      - ``marker_id`` — идентификатор инцидента (обязателен);
      - ``members`` — список участников с полями ``member_type`` и ``member_id`` (необязательно).

    Если канал существует, возвращает его ID. При создании канала добавляет
    указанных участников.
    """
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    marker_id = payload.get("marker_id")
    if not marker_id:
        return jsonify({"error": "marker_id is required"}), 400
    try:
        marker_id_int = int(marker_id)
    except Exception:
        return jsonify({"error": "marker_id must be integer"}), 400
    ch = Channel.query.filter_by(type="incident", marker_id=marker_id_int).first()
    if not ch:
        ch = Channel(type="incident", marker_id=marker_id_int, created_at=datetime.utcnow())
        db.session.add(ch)
        db.session.commit()
    members = payload.get("members") or []
    for m in members:
        try:
            mtype = str(m.get("member_type")).strip()
            mid = str(m.get("member_id")).strip()
        except Exception:
            continue
        if not mtype or not mid:
            continue
        existing = ChannelMember.query.filter_by(channel_id=ch.id, member_type=mtype, member_id=mid).first()
        if not existing:
            cm = ChannelMember(channel_id=ch.id, member_type=mtype, member_id=mid)
            db.session.add(cm)
    if members:
        db.session.commit()
    return jsonify({"id": ch.id, "type": ch.type, "marker_id": ch.marker_id}), 200


@bp.post("/ensure_dm_channel")
def api_chat_ensure_dm_channel():
    """Получить или создать direct message (DM) канал между администратором и устройством.

    Ожидает JSON:
      - ``device_id`` — идентификатор устройства (обязателен).

    Если канал DM с указанным устройством и текущим админом существует, возвращает его ID.
    Иначе создаёт новый канал и добавляет двух участников.
    """
    require_admin("editor")
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    device_id = str(payload.get("device_id") or "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    # Определяем идентификатор текущего админа
    admin_id = str(session.get("admin_id") or session.get("username") or "admin")
    # Ищем существующий DM канал с этими участниками
    channels = Channel.query.filter_by(type="dm").all()
    for ch in channels:
        members = {(cm.member_type, cm.member_id) for cm in ch.members}
        if ("admin", admin_id) in members and ("tracker", device_id) in members:
            return jsonify({"id": ch.id, "type": ch.type}), 200
    # Создаём новый DM канал
    ch = Channel(type="dm", created_at=datetime.utcnow())
    db.session.add(ch)
    db.session.commit()
    # Добавляем участников
    cm_admin = ChannelMember(channel_id=ch.id, member_type="admin", member_id=admin_id)
    cm_dev = ChannelMember(channel_id=ch.id, member_type="tracker", member_id=device_id)
    db.session.add(cm_admin)
    db.session.add(cm_dev)
    db.session.commit()
    return jsonify({"id": ch.id, "type": ch.type}), 201


@bp.post("/admin/purge")
def api_chat_admin_purge():
    """Удалить сообщения старше указанного числа дней и файлы.

    Ожидает JSON:
      - ``days`` — сколько дней хранить (по умолчанию ``CHAT2_RETENTION_DAYS`` или 90);
      - ``dry_run`` — если True, просто вернуть количество, не удаляя.
    """
    require_admin("superadmin")
    payload: Dict[str, Any] = request.get_json(silent=True, force=True) or {}
    days = payload.get("days")
    dry_run = bool(payload.get("dry_run"))
    try:
        days_int = int(days) if days is not None else int(current_app.config.get("CHAT2_RETENTION_DAYS", 90))
    except Exception:
        days_int = int(current_app.config.get("CHAT2_RETENTION_DAYS", 90))
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days_int)
    old_msgs = Message.query.filter(Message.created_at < cutoff).all()
    count = len(old_msgs)
    if dry_run:
        return jsonify({"would_delete": count})
    # Удаляем медиа файлы
    upload_root = current_app.config.get("UPLOAD_FOLDER") or "uploads"
    deleted_files = 0
    for msg in old_msgs:
        if msg.media_key:
            path = os.path.join(upload_root, msg.media_key)
            try:
                os.remove(path)
                deleted_files += 1
            except Exception:
                pass
        db.session.delete(msg)
    db.session.commit()
    return jsonify({"deleted_messages": count, "deleted_files": deleted_files}), 200


@bp.get("/metrics")
def api_chat_metrics():
    """Метрики chat2 в формате JSON."""
    require_admin("viewer")
    from .metrics import snapshot as chat_snapshot
    return jsonify(chat_snapshot())
