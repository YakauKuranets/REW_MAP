"""Сервисный слой для чата.

Здесь сосредоточена бизнес‑логика работы чата между администратором
и пользователями Telegram‑бота.

Функциональность:

- список диалогов (conversations) с последним сообщением, статусом и
  счётчиком непрочитанных сообщений для администратора;
- загрузка истории переписки с конкретным пользователем;
- отправка сообщений от администратора или пользователя;
- изменение статуса диалога и отметка сообщений как прочитанных.
"""

from datetime import datetime
import os

import requests
from typing import List, Dict, Any, Optional

from sqlalchemy import func
from compat_flask import current_app

from ..models import db, ChatMessage, ChatDialog
from ..sockets import broadcast_event_sync


# -------------------------------------------------------------
# Вспомогательные функции
# -------------------------------------------------------------


def _make_display_name(user_id: str, username: Optional[str] = None,
                       first_name: Optional[str] = None, last_name: Optional[str] = None) -> str:
    """Сформировать человекочитаемое имя пользователя.

    Требование проекта: в админ-чате нужно показывать "ник" Telegram,
    а не голые цифры ID.
    """
    user_id = str(user_id)
    username = (username or '').strip().lstrip('@') or None
    first_name = (first_name or '').strip() or None
    last_name = (last_name or '').strip() or None

    if username:
        return '@' + username
    if first_name and last_name:
        return f"{first_name} {last_name}".strip()
    if first_name:
        return first_name
    # fallback
    return f"Пользователь {user_id}"


def _apply_profile_to_dialog(dialog: ChatDialog, profile: Optional[Dict[str, Any]]) -> bool:
    """Обновить поля Telegram-профиля в диалоге.

    Возвращает True, если что-то изменилось.
    """
    if not profile:
        return False

    username = (profile.get('username') or profile.get('tg_username') or '').strip()
    first_name = (profile.get('first_name') or profile.get('tg_first_name') or '').strip()
    last_name = (profile.get('last_name') or profile.get('tg_last_name') or '').strip()

    changed = False

    # username храним без '@'
    username_clean = username.lstrip('@').strip() or None
    if username_clean and dialog.tg_username != username_clean:
        dialog.tg_username = username_clean
        changed = True

    if first_name and dialog.tg_first_name != first_name:
        dialog.tg_first_name = first_name
        changed = True

    if last_name and dialog.tg_last_name != last_name:
        dialog.tg_last_name = last_name
        changed = True

    # display_name — человекочитаемое отображение
    new_display = (profile.get('display_name') or '').strip() or _make_display_name(
        dialog.user_id,
        username=username_clean,
        first_name=first_name,
        last_name=last_name,
    )
    if new_display and dialog.display_name != new_display:
        dialog.display_name = new_display
        changed = True

    return changed


def _get_or_create_dialog(user_id: str, profile: Optional[Dict[str, Any]] = None) -> ChatDialog:
    """Получить или создать запись диалога для указанного пользователя."""
    user_id = str(user_id)
    dialog = ChatDialog.query.get(user_id)
    if dialog is None:
        dialog = ChatDialog(user_id=user_id, status='new')
        db.session.add(dialog)

    # Применяем профиль (если пришёл)
    _apply_profile_to_dialog(dialog, profile)
    return dialog


# -------------------------------------------------------------
# Публичное API сервиса
# -------------------------------------------------------------


def list_conversations(status: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    """Вернуть список диалогов.

    Каждый элемент содержит:

    - ``user_id`` — идентификатор пользователя бота;
    - ``last_message`` — словарь с полями ``text``, ``sender``,
      ``created_at``;
    - ``status`` — статус диалога: ``new`` | ``in_progress`` | ``closed``;
    - ``unread`` — количество непрочитанных сообщений для администратора.

    :param status: необязательный фильтр по статусу диалога.
    :param limit: лимит строк (пагинация).
    :param offset: смещение (пагинация).
    """
    # Находим время последнего сообщения по каждому пользователю
    subq = (
        db.session.query(
            ChatMessage.user_id.label("user_id"),
            func.max(ChatMessage.created_at).label("last_time"),
        )
        .group_by(ChatMessage.user_id)
        .subquery()
    )

    query = (
        db.session.query(
            subq.c.user_id,
            ChatMessage.text,
            ChatMessage.sender,
            subq.c.last_time,
            ChatDialog.status,
            ChatDialog.unread_for_admin,
            ChatDialog.display_name,
            ChatDialog.tg_username,
            ChatDialog.tg_first_name,
            ChatDialog.tg_last_name,
        )
        .join(
            ChatMessage,
            (ChatMessage.user_id == subq.c.user_id)
            & (ChatMessage.created_at == subq.c.last_time),
        )
        .outerjoin(ChatDialog, ChatDialog.user_id == subq.c.user_id)
        .order_by(subq.c.last_time.desc())
    )

    if status:
        # Если статус явно указан, фильтруем по нему.
        # Диалоги без явной записи считаем "new".
        status = status.strip()
        if status == "new":
            query = query.filter(
                (ChatDialog.status == "new") | (ChatDialog.status.is_(None))
            )
        else:
            query = query.filter(ChatDialog.status == status)

    # Пагинация (best-effort): даже если админ-чата станет очень много,
    # не будем тянуть всё в один ответ.
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 200
    try:
        offset_i = int(offset)
    except Exception:
        offset_i = 0
    limit_i = max(1, min(limit_i, 2000))
    offset_i = max(0, offset_i)
    query = query.offset(offset_i).limit(limit_i)

    rows = query.all()

    result: List[Dict[str, Any]] = []
    seen_users = set()

    for user_id, text, sender, last_time, dlg_status, unread_for_admin, dlg_display_name, dlg_tg_username, dlg_first_name, dlg_last_name in rows:
        user_id_str = str(user_id)
        if user_id_str in seen_users:
            continue
        seen_users.add(user_id_str)

        # Если счётчик непрочитанных не хранится в ChatDialog, считаем по сообщениям
        if unread_for_admin is None:
            unread = (
                db.session.query(func.count(ChatMessage.id))
                .filter(
                    ChatMessage.user_id == user_id_str,
                    ChatMessage.sender == "user",
                    ChatMessage.is_read == False,  # noqa: E712
                )
                .scalar()
            ) or 0
        else:
            unread = unread_for_admin or 0

        # Эффективный статус: если нет записи — считаем new/in_progress по unread
        if dlg_status:
            effective_status = dlg_status
        else:
            effective_status = "new" if unread > 0 else "in_progress"

        # Формируем display_name из сохранённого Telegram-профиля.
        display_name = dlg_display_name or _make_display_name(
            user_id_str,
            username=dlg_tg_username,
            first_name=dlg_first_name,
            last_name=dlg_last_name,
        )

        result.append(
            {
                "user_id": user_id_str,
                "display_name": display_name,
                # Для совместимости с текущим фронтом (chat.js)
                "last_text": text,
                "last_sender": sender,
                "last_message": {
                    "text": text,
                    "sender": sender,
                    "created_at": last_time.isoformat() if last_time else None,
                },
                "status": effective_status,
                "unread": int(unread),
            }
        )

    return result


def get_history(user_id: str, mark_as_read: bool = True) -> List[Dict[str, Any]]:
    """Вернуть историю сообщений для указанного пользователя.

    Сообщения упорядочены по времени. По умолчанию все сообщения
    от пользователя помечаются как прочитанные администратором.
    """
    user_id = str(user_id)
    msgs = (
        ChatMessage.query.filter_by(user_id=user_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )

    if mark_as_read:
        (
            ChatMessage.query.filter_by(user_id=user_id, sender="user", is_read=False)
            .update({"is_read": True}, synchronize_session=False)
        )
        dialog = _get_or_create_dialog(user_id)
        dialog.unread_for_admin = 0
        if dialog.status == "new":
            dialog.status = "in_progress"
        db.session.commit()

    return [m.to_dict() for m in msgs]



def get_history_paged(
    user_id: str,
    *,
    limit: int = 500,
    offset: int = 0,
    tail: bool = True,
    mark_as_read: bool = True,
) -> List[Dict[str, Any]]:
    """Вернуть историю сообщений с пагинацией.

    Поведение:
      - если tail=True: возвращает последние N сообщений (limit), в порядке ASC
      - если tail=False: возвращает страницу ASC (offset/limit)

    По умолчанию, как и раньше, все сообщения пользователя помечаются прочитанными
    администратором (mark_as_read=True).
    """
    user_id = str(user_id)

    try:
        limit = int(limit)
    except Exception:
        limit = 500
    try:
        offset = int(offset)
    except Exception:
        offset = 0

    limit = max(1, min(limit, 5000))
    offset = max(0, offset)

    q = ChatMessage.query.filter_by(user_id=user_id)

    if tail:
        # последние N сообщений: берём DESC, затем разворачиваем
        rows = (
            q.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
            .all()
        )
        msgs = list(reversed(rows))
    else:
        msgs = (
            q.order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    if mark_as_read:
        (
            ChatMessage.query.filter_by(user_id=user_id, sender="user", is_read=False)
            .update({"is_read": True}, synchronize_session=False)
        )
        dialog = _get_or_create_dialog(user_id)
        dialog.unread_for_admin = 0
        if dialog.status == "new":
            dialog.status = "in_progress"
        db.session.commit()

    return [m.to_dict() for m in msgs]



def get_history_before(
    user_id: str,
    *,
    before_id: int,
    limit: int = 200,
    mark_as_read: bool = False,
) -> List[Dict[str, Any]]:
    """Вернуть страницу сообщений, которые *старше* сообщения before_id.

    Используется для infinite-scroll вверх в админском UI:
      - на клиенте хранится id самого первого сообщения на экране;
      - при прокрутке вверх запрашиваем N сообщений, которые были раньше.

    Возвращает сообщения в порядке ASC (от старых к новым).
    """
    from sqlalchemy import and_, or_

    try:
        limit = max(1, min(2000, int(limit)))
    except Exception:
        limit = 200

    ref = ChatMessage.query.filter_by(user_id=user_id, id=int(before_id)).first()
    if not ref:
        return []

    q = ChatMessage.query.filter(ChatMessage.user_id == user_id).filter(
        or_(
            ChatMessage.created_at < ref.created_at,
            and_(ChatMessage.created_at == ref.created_at, ChatMessage.id < ref.id),
        )
    )

    rows = (
        q.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    msgs = list(reversed(rows))

    if mark_as_read:
        (
            ChatMessage.query.filter_by(user_id=user_id, sender="user", is_read=False)
            .update({"is_read": True}, synchronize_session=False)
        )
        dialog = _get_or_create_dialog(user_id)
        dialog.unread_for_admin = 0
        if dialog.status == "new":
            dialog.status = "in_progress"
        db.session.commit()

    return [m.to_dict() for m in msgs]


def send_message(user_id: str, text: str, sender: str = "admin", profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Создать сообщение и при необходимости отправить его в Telegram.

    :param user_id: идентификатор пользователя Telegram
    :param text: текст сообщения
    :param sender: `'user'` или `'admin'`
    :return: словарь с данными созданного сообщения
    """
    user_id = str(user_id)
    sender = (sender or "admin").strip() or "admin"

    # Важно: сначала получаем/создаём диалог.
    # Если сначала добавить ChatMessage в session, то следующий SELECT может вызвать
    # autoflush и попытку INSERT ещё до того, как мы подготовили БД/схему.
    # Это особенно критично для старых SQLite баз, где могло не быть новых колонок.
    with db.session.no_autoflush:
        dialog = _get_or_create_dialog(user_id, profile=profile)

    msg = ChatMessage(user_id=user_id, sender=sender, text=text)
    # Сообщения пользователя по умолчанию считаем непрочитанными для админа
    if sender == "user":
        msg.is_read = False
    db.session.add(msg)

    dialog.last_message_at = msg.created_at or datetime.utcnow()

    if sender == "user":
        dialog.unread_for_admin = (dialog.unread_for_admin or 0) + 1
        # Если диалог был закрыт — переводим в работу
        if dialog.status == "closed":
            dialog.status = "in_progress"
    else:
        dialog.unread_for_user = (dialog.unread_for_user or 0) + 1
        if dialog.status in ("new", "closed"):
            dialog.status = "in_progress"

    db.session.commit()

    # Если отправитель админ — пробуем отправить в Telegram
    if sender == "admin":
        try:
            ok, err = send_telegram_message(user_id, text)
            if not ok:
                current_app.logger.warning(
                    "Не удалось отправить сообщение пользователю %s: %s",
                    user_id,
                    err,
                )

            else:
                # Если доставка в Telegram успешна, помечаем как уведомлённое,
                # чтобы polling бота не прислал дубликат.
                try:
                    dialog.last_notified_admin_msg_id = int(msg.id)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
        except Exception:  # pragma: no cover
            current_app.logger.exception(
                "Ошибка при попытке отправки сообщения пользователю %s", user_id
            )

    # Транслируем в WebSocket
    try:
        broadcast_event_sync("chat_message", msg.to_dict())
    except Exception:  # pragma: no cover
        current_app.logger.exception("Ошибка при отправке события WebSocket")

    return msg.to_dict()


def set_status(user_id: str, status: str) -> Dict[str, Any]:
    """Установить статус диалога.

    Допустимые статусы: ``new``, ``in_progress``, ``closed``.
    Возвращает словарь с данными диалога.
    """
    user_id = str(user_id)
    status = (status or "").strip()
    allowed = {"new", "in_progress", "closed"}
    if status not in allowed:
        raise ValueError(f"Unsupported status: {status!r}")

    dialog = _get_or_create_dialog(user_id)
    dialog.status = status
    db.session.commit()
    return dialog.to_dict()


def mark_read_by_admin(user_id: str) -> Dict[str, Any]:
    """Пометить все сообщения пользователя как прочитанные администратором."""
    user_id = str(user_id)
    (
        ChatMessage.query.filter_by(user_id=user_id, sender="user", is_read=False)
        .update({"is_read": True}, synchronize_session=False)
    )
    dialog = _get_or_create_dialog(user_id)
    dialog.unread_for_admin = 0
    if dialog.status == "new":
        dialog.status = "in_progress"
    db.session.commit()
    return dialog.to_dict()

# -------------------------------------------------------------
# Операции очистки истории
# -------------------------------------------------------------

def clear_history(user_id: str) -> Dict[str, Any]:
    """Удалить все сообщения чата для указанного пользователя.

    Возвращает словарь с количеством удалённых сообщений и текущим
    состоянием диалога. Если диалог не существует, он будет создан
    заново с нулевыми счётчиками и статусом ``in_progress``.

    :param user_id: идентификатор пользователя Telegram
    :return: словарь с полем ``deleted`` и ``dialog``
    """
    user_id = str(user_id)
    # Считаем количество удаляемых сообщений, а затем удаляем их
    count = ChatMessage.query.filter_by(user_id=user_id).delete()
    # Получаем или создаём диалог
    dialog = _get_or_create_dialog(user_id)
    # Сбрасываем счётчики и статус
    dialog.unread_for_admin = 0
    dialog.unread_for_user = 0
    dialog.last_notified_admin_msg_id = 0
    dialog.last_seen_admin_msg_id = 0
    dialog.status = 'in_progress'
    dialog.last_message_at = datetime.utcnow()
    db.session.commit()
    # Транслируем событие о том, что сообщения удалены
    try:
        broadcast_event_sync('chat_cleared', {'user_id': user_id, 'deleted': count})
    except Exception:
        current_app.logger.exception('Ошибка при отправке события очистки чата')
    return {'deleted': count, 'dialog': dialog.to_dict()}


def delete_dialog(user_id: str) -> Dict[str, Any]:
    """Удалить диалог полностью (сообщения + запись диалога).

    В отличие от clear_history, удаляет и ChatDialog. Это полезно, если
    хочется "полностью убрать переписку" из системы.
    """
    user_id = str(user_id)
    deleted_messages = ChatMessage.query.filter_by(user_id=user_id).delete()
    deleted_dialog = ChatDialog.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    try:
        broadcast_event_sync('chat_deleted', {'user_id': user_id})
    except Exception:
        current_app.logger.exception('Ошибка при отправке события удаления диалога')
    return {'deleted_messages': int(deleted_messages or 0), 'deleted_dialog': int(deleted_dialog or 0)}


# -------------------------------------------------------------
# Интеграция с Telegram
# -------------------------------------------------------------


def send_telegram_message(user_id: str, text: str):
    """Отправить сообщение пользователю через Telegram Bot API.

    Используется для уведомления пользователя, когда администратор отвечает
    ему с сайта (web-admin чата).

    Токен берём из переменных окружения (как в bot.py):
    ``MAP_BOT_TOKEN`` или ``BOT_TOKEN``.

    Возвращает пару ``(ok: bool, error: Optional[str])``.
    """
    token = (os.getenv("MAP_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        return False, "MAP_BOT_TOKEN / BOT_TOKEN is not set"

    user_id_str = str(user_id).strip()
    if not user_id_str.isdigit():
        return False, f"Invalid user_id: {user_id_str!r}"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": int(user_id_str),
        # Небольшой префикс — чтобы пользователь понимал, что это ответ админа
        "text": f"💬 Ответ от администратора:\n{text}",
        "disable_web_page_preview": True,
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        if not data.get("ok"):
            return False, f"Telegram API error: {data}"
        return True, None
    except Exception as e:  # pragma: no cover
        return False, str(e)


# -------------------------------------------------------------
# Уведомления для пользователя (polling ботом)
# -------------------------------------------------------------

def list_notify_targets(limit: int = 200) -> List[Dict[str, Any]]:
    """Список пользователей, которым нужно прислать уведомление (для Telegram-бота).

    Уведомление != прочтение:
      - last_notified_admin_msg_id: до какого id мы уже УВЕДОМИЛИ (anti-duplicate)
      - last_seen_admin_msg_id: до какого id пользователь реально ПОСМОТРЕЛ (для счётчика)

    Здесь возвращаем тех, у кого есть новые сообщения админа, которые ещё НЕ уведомлены.
    """
    try:
        lim = max(1, min(int(limit or 200), 1000))

        subq = (
            db.session.query(
                ChatMessage.user_id.label("user_id"),
                func.max(ChatMessage.id).label("max_admin_id"),
            )
            .filter(ChatMessage.sender == "admin")
            .group_by(ChatMessage.user_id)
            .subquery()
        )

        q = (
            db.session.query(ChatDialog, subq.c.max_admin_id)
            .join(subq, subq.c.user_id == ChatDialog.user_id)
            .filter(subq.c.max_admin_id > ChatDialog.last_notified_admin_msg_id)
            .order_by(ChatDialog.last_message_at.desc())
            .limit(lim)
        )
        rows = q.all()
    except Exception:
        current_app.logger.exception("Failed to list notify targets")
        return []

    items: List[Dict[str, Any]] = []
    for dialog, max_admin_id in rows:
        display = dialog.display_name or _make_display_name(
            dialog.user_id,
            username=dialog.tg_username,
            first_name=dialog.tg_first_name,
            last_name=dialog.tg_last_name,
        )
        items.append({
            "user_id": str(dialog.user_id),
            "display_name": display,
            "max_admin_id": int(max_admin_id or 0),
            "unread_for_user": int(dialog.unread_for_user or 0),
            "last_message_at": dialog.last_message_at.isoformat() if dialog.last_message_at else None,
        })
    return items

def get_pending_admin_messages(user_id: str, limit: int = 10) -> Dict[str, Any]:
    """Вернуть новые сообщения от админа, которые ещё не были уведомлены пользователю.

    Используем cursor = last_notified_admin_msg_id из ChatDialog.
    """
    user_id = str(user_id)
    dialog = _get_or_create_dialog(user_id)

    last_id = int(getattr(dialog, "last_notified_admin_msg_id", 0) or 0)
    lim = max(1, min(int(limit or 10), 50))

    msgs = (
        ChatMessage.query
        .filter(ChatMessage.user_id == user_id, ChatMessage.sender == "admin", ChatMessage.id > last_id)
        .order_by(ChatMessage.id.asc())
        .limit(lim)
        .all()
    )

    cursor = last_id
    if msgs:
        cursor = int(msgs[-1].id)

    return {
        "user_id": user_id,
        "cursor": cursor,
        "messages": [m.to_dict() for m in msgs],
        "count": len(msgs),
        "unread_for_user": int(dialog.unread_for_user or 0),
    }


def ack_admin_notified(user_id: str, cursor: int) -> Dict[str, Any]:
    """Подтвердить, что бот уведомил пользователя о сообщениях до cursor (id включительно).

    Не трогаем unread_for_user — это счётчик "непрочитано"; он сбрасывается только
    когда пользователь открыл переписку в боте (seen_admin).
    """
    user_id = str(user_id)
    dialog = _get_or_create_dialog(user_id)

    try:
        cur = int(cursor or 0)
    except Exception:
        cur = 0

    prev = int(getattr(dialog, "last_notified_admin_msg_id", 0) or 0)
    if cur > prev:
        dialog.last_notified_admin_msg_id = cur

    db.session.commit()
    return dialog.to_dict()



def get_unread_for_user(user_id: str) -> Dict[str, Any]:
    """Вернуть количество непрочитанных сообщений от админа для пользователя."""
    user_id = str(user_id)
    dialog = _get_or_create_dialog(user_id)

    try:
        last_seen = int(getattr(dialog, "last_seen_admin_msg_id", 0) or 0)
    except Exception:
        last_seen = 0

    try:
        unread = (
            db.session.query(func.count(ChatMessage.id))
            .filter(ChatMessage.user_id == user_id, ChatMessage.sender == "admin", ChatMessage.id > last_seen)
            .scalar()
        ) or 0
    except Exception:
        unread = int(dialog.unread_for_user or 0)

    try:
        dialog.unread_for_user = int(unread)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {"user_id": user_id, "unread_for_user": int(unread)}


def mark_seen_admin(user_id: str, cursor: int) -> Dict[str, Any]:
    """Пометить сообщения админа как просмотренные пользователем до cursor (id включительно)."""
    user_id = str(user_id)
    dialog = _get_or_create_dialog(user_id)

    try:
        cur = int(cursor or 0)
    except Exception:
        cur = 0

    prev = int(getattr(dialog, "last_seen_admin_msg_id", 0) or 0)
    if cur > prev:
        dialog.last_seen_admin_msg_id = cur

    try:
        last_seen = int(getattr(dialog, "last_seen_admin_msg_id", 0) or 0)
        unread = (
            db.session.query(func.count(ChatMessage.id))
            .filter(ChatMessage.user_id == user_id, ChatMessage.sender == "admin", ChatMessage.id > last_seen)
            .scalar()
        ) or 0
        dialog.unread_for_user = int(unread)
    except Exception:
        dialog.unread_for_user = 0
    dialog.last_notified_admin_msg_id = 0
    dialog.last_seen_admin_msg_id = 0

    db.session.commit()
    return dialog.to_dict()
