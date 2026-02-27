"""Модели для событийного чата.

Эти модели описывают структуры данных для нового мессенджера:

- :class:`Channel` — канал, объединяющий участников по смене,
  инциденту или индивидуальной переписке. Использует ULID/UUID
  в качестве первичного ключа.
- :class:`Message` — отдельное сообщение в канале. Содержит
  информацию об авторе, тексте, типе и времени создания.
- :class:`ChannelMember` — привязка пользователя (админ или устройство)
  к каналу с отметкой, до какого сообщения он дочитал.

В настоящий момент модели задают минимальный набор полей для
отправки и получения текстовых сообщений. В дальнейшем можно
расширить их медиавложениями, счётчиками доставленных/прочитанных
и другими метаданными.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from ..extensions import db


class Channel(db.Model):
    """Канал общения.

    Использует строковый первичный ключ (UUID4) для удобства
    распределённой генерации и сортировки. Поле ``type`` задаёт
    разновидность канала: ``shift`` (смена), ``incident`` (инцидент)
    или ``dm`` (прямое сообщение). ``shift_id`` и ``marker_id``
    хранят идентификаторы соответствующих сущностей, если применимо.
    """

    __tablename__ = "chat2_channels"
    id: str = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type: str = db.Column(db.String(16), nullable=False)
    shift_id: Optional[int] = db.Column(db.Integer, nullable=True)
    marker_id: Optional[int] = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_message_at = db.Column(db.DateTime, nullable=True)

    messages = db.relationship("Message", backref="channel", lazy="dynamic")
    members = db.relationship("ChannelMember", backref="channel", lazy="dynamic")


class Message(db.Model):
    """Сообщение в канале.

    ``id`` — первичный ключ (UUID4), ``channel_id`` — FK на
    канал. ``sender_type`` — строка (например, ``admin`` или
    ``tracker``); ``sender_id`` хранит идентификатор отправителя
    (admin_user_id или device_id). ``client_msg_id`` —
    идентификатор, присвоенный клиентом для идемпотентности. ``text``
    — текст сообщения; ``kind`` может быть ``text``, ``system``
    и т.п. ``created_at`` хранит время создания на сервере.
    """

    __tablename__ = "chat2_messages"
    id: str = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id: str = db.Column(db.String(36), db.ForeignKey("chat2_channels.id"), nullable=False)
    sender_type: str = db.Column(db.String(16), nullable=False)
    sender_id: str = db.Column(db.String(64), nullable=False)
    client_msg_id: Optional[str] = db.Column(db.String(64), nullable=True)
    text: Optional[str] = db.Column(db.Text, nullable=True)
    kind: str = db.Column(db.String(16), nullable=False, default="text")
    # Поля для медиа. media_key хранит путь или ключ объекта (например, файл в R2);
    # mime — MIME‑тип; size — размер файла в байтах; thumb_key — ключ для
    # эскиза (опционально).
    media_key: Optional[str] = db.Column(db.String(256), nullable=True)
    mime: Optional[str] = db.Column(db.String(64), nullable=True)
    size: Optional[int] = db.Column(db.Integer, nullable=True)
    thumb_key: Optional[str] = db.Column(db.String(256), nullable=True)

    # Счётчики доставки (сколько участников получили / прочитали)
    delivered_count: int = db.Column(db.Integer, nullable=False, default=0)
    read_count: int = db.Column(db.Integer, nullable=False, default=0)
    # Дополнительные метаданные (например, идентификатор шаблона). Храним JSON для
    # гибкого расширения. В SQLite используем Text, в других СУБД — JSON.
    meta_json: Optional[dict] = db.Column(db.JSON().with_variant(db.Text(), "sqlite"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index("ix_chat2_messages_channel_created", "channel_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "sender_type": self.sender_type,
            "sender_id": self.sender_id,
            "client_msg_id": self.client_msg_id,
            "text": self.text,
            "kind": self.kind,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "media_key": self.media_key,
            "mime": self.mime,
            "size": self.size,
            "thumb_key": self.thumb_key,
            "delivered_count": self.delivered_count,
            "read_count": self.read_count,
            "meta_json": self.meta_json,
        }


class ChannelMember(db.Model):
    """Связка пользователя/устройства и канала.

    Позволяет хранить, до какого сообщения участник дочитал, и
    использовать эти данные для подсчёта непрочитанных. ``member_type``
    может быть ``admin`` или ``tracker``; ``member_id`` хранит
    соответствующий идентификатор (admin_user.id или device_id).
    """

    __tablename__ = "chat2_members"
    id = db.Column(db.Integer, primary_key=True)
    channel_id: str = db.Column(db.String(36), db.ForeignKey("chat2_channels.id"), nullable=False)
    member_type: str = db.Column(db.String(16), nullable=False)
    member_id: str = db.Column(db.String(64), nullable=False)
    last_read_message_id: Optional[str] = db.Column(db.String(36), nullable=True)
    last_read_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("channel_id", "member_type", "member_id", name="uq_chat2_members_member"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "member_type": self.member_type,
            "member_id": self.member_id,
            "last_read_message_id": self.last_read_message_id,
            "last_read_at": self.last_read_at.isoformat() if self.last_read_at else None,
        }


# Хранилище push‑токенов
class PushToken(db.Model):
    """Push‑токены для участников чатов.

    Позволяет отправлять push‑уведомления участникам. Один участник может
    иметь несколько токенов (например, разные устройства)."""

    __tablename__ = "chat2_push_tokens"
    id = db.Column(db.Integer, primary_key=True)
    member_type = db.Column(db.String(16), nullable=False)  # admin или tracker
    member_id = db.Column(db.String(64), nullable=False)
    token = db.Column(db.String(256), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("member_type", "member_id", "token", name="uq_chat2_push_member_token"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "member_type": self.member_type,
            "member_id": self.member_id,
            "token": self.token,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
