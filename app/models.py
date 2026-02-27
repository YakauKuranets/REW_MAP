"""
Модели базы данных для приложения.

В данный момент определена только модель Zone. Если впоследствии
понадобится сохранять адреса, можно добавить модель Address и
соответствующие отношения.
"""

import base64
import hashlib
import json
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

try:
    from geoalchemy2 import Geometry
except Exception:  # pragma: no cover - fallback for environments without GeoAlchemy2
    from sqlalchemy.types import UserDefinedType

    class Geometry(UserDefinedType):
        def __init__(self, geometry_type: str = "POINT", srid: int = 4326):
            self.geometry_type = geometry_type
            self.srid = srid

        def get_col_spec(self, **kw):
            return "GEOMETRY"

from sqlalchemy import func
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.mutable import MutableDict

from .extensions import db


from datetime import datetime, timezone


def _video_credentials_fernet() -> Fernet:
    """Return Fernet instance for terminal auth credentials.

    Key priority:
    1) VIDEO_AUTH_CREDENTIALS_KEY (already base64 urlsafe 32-byte key)
    2) Derived key from SECRET_KEY
    """
    raw_key = (os.environ.get("VIDEO_AUTH_CREDENTIALS_KEY") or "").strip()
    if raw_key:
        return Fernet(raw_key.encode("utf-8"))

    secret = (os.environ.get("SECRET_KEY") or "dev-insecure-secret").encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_terminal_auth_credentials(payload: Dict[str, Any]) -> str:
    """Encrypt terminal auth credentials dict before storing in DB."""
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    return _video_credentials_fernet().encrypt(data).decode("utf-8")


def decrypt_terminal_auth_credentials(token: str) -> Dict[str, Any]:
    """Decrypt terminal auth credentials token from DB into dict."""
    if not token:
        return {}
    try:
        data = _video_credentials_fernet().decrypt(token.encode("utf-8"))
        decoded = json.loads(data.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {}
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _is_postgres_bound() -> bool:
    bind = db.session.get_bind() if db.session else None
    return bool(bind is not None and bind.dialect.name == 'postgresql')

# ---------------------------------------------------------------------------
# Администраторы и роли
# ---------------------------------------------------------------------------


admin_zones = db.Table(
    'admin_zones',
    db.Column('admin_id', db.Integer, db.ForeignKey('admin_users.id'), primary_key=True),
    db.Column('zone_id', db.Integer, db.ForeignKey('zone.id'), primary_key=True),
)


class AdminUser(db.Model):
    """Администратор веб-интерфейса.

    Позволяет хранить несколько админов с разными ролями и
    привязкой к зонам. Пароли хранятся в виде хешей, как и в
    конфигурации бота/сайта.
    """

    __tablename__ = 'admin_users'
    __table_args__ = (
        db.Index('ix_admin_users_username', 'username'),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default='editor')  # viewer|editor|superadmin
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Связь с зонами, к которым админ имеет доступ
    zones = db.relationship('Zone', secondary=admin_zones, backref='admins')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'zones': [z.id for z in self.zones],
        }


class Address(db.Model):
    """Модель адреса (точки на карте). Содержит координаты,
    название, описание, статус, категорию, ссылку и имя файла фото.

    После миграции на базу данных адреса хранятся не в JSON,
    а в таблице, что позволяет выполнять поиск и фильтрацию
    средствами SQLAlchemy. Даты создания и обновления позволяют
    отслеживать изменения.
    """

    __tablename__ = 'addresses'
    __table_args__ = (
        # Индекс по категории и статусу для быстрых фильтров на карте
        db.Index('ix_addresses_category_status', 'category', 'status'),
        # Индекс по дате создания для сортировки и аналитики
        db.Index('ix_addresses_created_at', 'created_at'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(255), nullable=False, default='')
    _lat: float = db.Column('lat', db.Float, nullable=True)
    _lon: float = db.Column('lon', db.Float, nullable=True)
    geom = db.Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    notes: str = db.Column(db.Text, nullable=True)
    status: str = db.Column(db.String(64), nullable=True)
    link: str = db.Column(db.String(512), nullable=True)
    category: str = db.Column(db.String(128), nullable=True)
    zone_id = db.Column(db.Integer, db.ForeignKey('zone.id'), nullable=True)
    zone = db.relationship('Zone', lazy='selectin')
    photo: str = db.Column(db.String(128), nullable=True)
    ai_tags = db.Column(db.JSON().with_variant(JSONB, 'postgresql'), nullable=True)
    priority = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @hybrid_property
    def lat(self) -> Optional[float]:
        return self._lat

    @lat.setter
    def lat(self, value: Optional[float]) -> None:
        self._lat = value
        if _is_postgres_bound() and self._lat is not None and self._lon is not None:
            self.geom = func.ST_SetSRID(func.ST_MakePoint(self._lon, self._lat), 4326)

    @lat.expression
    def lat(cls):
        return cls._lat

    @hybrid_property
    def lon(self) -> Optional[float]:
        return self._lon

    @lon.setter
    def lon(self, value: Optional[float]) -> None:
        self._lon = value
        if _is_postgres_bound() and self._lat is not None and self._lon is not None:
            self.geom = func.ST_SetSRID(func.ST_MakePoint(self._lon, self._lat), 4326)

    @lon.expression
    def lon(cls):
        return cls._lon

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать запись в словарь для JSON‑выдачи."""
        return {
            'id': self.id,
            'name': self.name,
            'lat': self.lat,
            'lon': self.lon,
            'notes': self.notes,
            'status': self.status,
            'link': self.link,
            'category': self.category,
            'zone_id': self.zone_id,
            'photo': self.photo,
            'ai_tags': self.ai_tags or [],
            'priority': self.priority,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class PendingMarker(db.Model):
    """Модель ожидающей заявки (pending marker).

    Ожидающая заявка создаётся, когда пользователь отправляет точку
    через телеграм‑бот. После одобрения администратора заявка
    переносится в таблицу Address. Неодобренные заявки хранятся
    отдельно, что позволяет фильтровать и управлять ими.
    """

    __tablename__ = 'pending_markers'
    __table_args__ = (
        db.Index('ix_pending_markers_status', 'status'),
        db.Index('ix_pending_markers_created_at', 'created_at'),
        db.Index('ix_pending_markers_user_id', 'user_id'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(255), nullable=False, default='')
    _lat: float = db.Column('lat', db.Float, nullable=True)
    _lon: float = db.Column('lon', db.Float, nullable=True)
    geom = db.Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    notes: str = db.Column(db.Text, nullable=True)
    status: str = db.Column(db.String(64), nullable=True)
    link: str = db.Column(db.String(512), nullable=True)
    category: str = db.Column(db.String(128), nullable=True)
    zone_id = db.Column(db.Integer, db.ForeignKey('zone.id'), nullable=True)
    zone = db.relationship('Zone', lazy='selectin')
    photo: str = db.Column(db.String(128), nullable=True)
    ai_tags = db.Column(db.JSON().with_variant(JSONB, 'postgresql'), nullable=True)
    priority = db.Column(db.Integer, nullable=True)
    # идентификатор пользователя бота или сообщения для трассировки
    user_id: str = db.Column(db.String(64), nullable=True)
    """Идентификатор пользователя, отправившего заявку через бот."""
    message_id: str = db.Column(db.String(64), nullable=True)
    """Идентификатор сообщения бота для связи с телеграм‑ответом."""
    reporter: str = db.Column(db.String(128), nullable=True)
    """Имя или контакт отправителя (может совпадать с user_id или быть строкой)."""
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @hybrid_property
    def lat(self) -> Optional[float]:
        return self._lat

    @lat.setter
    def lat(self, value: Optional[float]) -> None:
        self._lat = value
        if _is_postgres_bound() and self._lat is not None and self._lon is not None:
            self.geom = func.ST_SetSRID(func.ST_MakePoint(self._lon, self._lat), 4326)

    @lat.expression
    def lat(cls):
        return cls._lat

    @hybrid_property
    def lon(self) -> Optional[float]:
        return self._lon

    @lon.setter
    def lon(self, value: Optional[float]) -> None:
        self._lon = value
        if _is_postgres_bound() and self._lat is not None and self._lon is not None:
            self.geom = func.ST_SetSRID(func.ST_MakePoint(self._lon, self._lat), 4326)

    @lon.expression
    def lon(cls):
        return cls._lon

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'lat': self.lat,
            'lon': self.lon,
            'notes': self.notes,
            'status': self.status,
            'link': self.link,
            'category': self.category,
            'zone_id': self.zone_id,
            'photo': self.photo,
            'ai_tags': self.ai_tags or [],
            'priority': self.priority,
            'user_id': self.user_id,
            'message_id': self.message_id,
            'reporter': self.reporter,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class PendingHistory(db.Model):
    """История действий с заявками.

    Каждая запись отражает изменение статуса pending‑заявки: одобрено,
    отклонено, отменено и т. д. Это упрощает аудит действий и
    позволяет восстановить адрес, к которому была перенесена
    заявка.
    """

    __tablename__ = 'pending_history'
    __table_args__ = (
        db.Index('ix_pending_history_pending_id', 'pending_id'),
        db.Index('ix_pending_history_timestamp', 'timestamp'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    pending_id: int = db.Column(db.Integer, nullable=False)
    status: str = db.Column(db.String(32), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    address_id: int = db.Column(db.Integer, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'pending_id': self.pending_id,
            'status': self.status,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'address_id': self.address_id,
        }


# ---------------------------------------------------------------------------
# Objects and Cameras (B1 feature)
# ---------------------------------------------------------------------------


class Terminal(db.Model):
    """Видео-терминал для live/archive каналов.

    Поле ``auth_credentials`` хранится в БД в зашифрованном виде (Fernet).
    """

    __tablename__ = 'terminals'
    __table_args__ = (
        db.Index('ix_terminals_ip', 'ip'),
        db.Index('ix_terminals_type', 'terminal_type'),
    )

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(255), nullable=False, default='')
    ip: str = db.Column(db.String(128), nullable=True)
    terminal_type: str = db.Column(db.String(64), nullable=True)
    archive_root_path: str = db.Column(db.String(512), nullable=True)
    _auth_credentials: str = db.Column('auth_credentials', db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def auth_credentials(self) -> Dict[str, Any]:
        return decrypt_terminal_auth_credentials(self._auth_credentials or '')

    @auth_credentials.setter
    def auth_credentials(self, value: Any) -> None:
        if value is None:
            self._auth_credentials = None
            return
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    self._auth_credentials = encrypt_terminal_auth_credentials(parsed)
                    return
            except Exception:
                # treat as pre-encrypted token
                self._auth_credentials = value
                return
        if isinstance(value, dict):
            self._auth_credentials = encrypt_terminal_auth_credentials(value)
            return
        self._auth_credentials = encrypt_terminal_auth_credentials({})

    def to_dict(self, *, include_auth_credentials: bool = False) -> Dict[str, Any]:
        payload = {
            'id': self.id,
            'name': self.name,
            'ip': self.ip,
            'terminal_type': self.terminal_type,
            'archive_root_path': self.archive_root_path,
            'has_auth_credentials': bool(self._auth_credentials),
        }
        # Security by default: never expose secrets in normal serialization.
        if include_auth_credentials:
            payload['auth_credentials'] = self.auth_credentials
        return payload

class Object(db.Model):
    """Произвольный объект/адрес с описанием и набором камер.

    Эта сущность расширяет концепцию Address: кроме координат и описания,
    объект может иметь несколько связанных камер. Поле ``tags`` используется
    для хранения типа объекта (например «Видеонаблюдение», «Домофон»,
    «Шлагбаум») или произвольных меток, разделённых запятой. Сопутствующие
    камеры хранятся в таблице :class:`ObjectCamera`.
    """

    __tablename__ = 'objects'
    __table_args__ = (
        db.Index('ix_objects_created_at', 'created_at'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(255), nullable=False, default='')
    lat: float = db.Column(db.Float, nullable=True)
    lon: float = db.Column(db.Float, nullable=True)
    description: str = db.Column(db.Text, nullable=True)
    tags: str = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    cameras = db.relationship(
        'ObjectCamera', backref='object', lazy='selectin', cascade='all, delete-orphan'
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'lat': self.lat,
            'lon': self.lon,
            'description': self.description,
            'tags': self.tags,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'cameras': [cam.to_dict() for cam in self.cameras],
        }


class ObjectCamera(db.Model):
    """Камера, связанная с объектом.

    Для каждого объекта может быть несколько камер. Поле ``type``
    определяет тип ссылки (например «rtsp», «hls», «web»). Поле ``label`` —
    человекочитаемое название камеры, например «Вход 1».
    """

    __tablename__ = 'object_cameras'
    __table_args__ = (
        db.Index('ix_object_cameras_object_id', 'object_id'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    object_id: int = db.Column(db.Integer, db.ForeignKey('objects.id'), nullable=False)
    label: str = db.Column(db.String(255), nullable=True)
    url: str = db.Column(db.String(512), nullable=False)
    type: str = db.Column(db.String(32), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'object_id': self.object_id,
            'label': self.label,
            'url': self.url,
            'type': self.type,
        }

# ---------------------------------------------------------------------------
# Incidents and related tables (B2 feature)
# ---------------------------------------------------------------------------

class Incident(db.Model):
    """Оперативный инцидент на карте.

    Инцидент может быть связан с конкретным объектом (адресом) или иметь
    только координаты/адрес, если объект ещё не создан. Поля ``lat`` и
    ``lon`` хранят координаты точки; ``address`` – человекочитаемый адрес;
    ``description`` – описание события; ``priority`` – целочисленный приоритет
    (1 – самый высокий); ``status`` – текущий статус жизненного цикла
    (``new``, ``assigned``, ``enroute``, ``on_scene``, ``resolved``, ``closed``).
    Тimestamps ``created_at`` и ``updated_at`` упрощают сортировку и
    аналитику. Отношения ``events`` и ``assignments`` содержат все связанные
    события и назначения нарядов.
    """

    __tablename__ = 'incidents'
    __table_args__ = (
        db.Index('ix_incidents_created_at', 'created_at'),
        db.Index('ix_incidents_status', 'status'),
        db.Index('ix_incidents_priority', 'priority'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    object_id: int = db.Column(db.Integer, db.ForeignKey('objects.id'), nullable=True, index=True)
    lat: float = db.Column(db.Float, nullable=True)
    lon: float = db.Column(db.Float, nullable=True)
    address: str = db.Column(db.String(255), nullable=True)
    description: str = db.Column(db.Text, nullable=True)
    priority: int = db.Column(db.Integer, nullable=True)
    status: str = db.Column(db.String(32), nullable=False, default='new')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Отношения
    object = db.relationship('Object', lazy='selectin')
    events = db.relationship('IncidentEvent', backref='incident', lazy='selectin', cascade='all, delete-orphan')
    assignments = db.relationship('IncidentAssignment', backref='incident', lazy='selectin', cascade='all, delete-orphan')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'object_id': self.object_id,
            'lat': self.lat,
            'lon': self.lon,
            'address': self.address,
            'description': self.description,
            'priority': self.priority,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'object': self.object.to_dict() if self.object else None,
            'assignments': [a.to_dict() for a in self.assignments],
            'events': [e.to_dict() for e in self.events],
        }


class IncidentEvent(db.Model):
    """Событие, связанное с инцидентом (таймлайн).

    Каждое событие хранит тип (``event_type``), произвольный JSON-пейлоад и
    временную отметку ``ts``. События записываются при создании
    инцидента, назначении наряда, смене статуса и других действиях.
    """

    __tablename__ = 'incident_events'
    __table_args__ = (
        db.Index('ix_incident_events_incident', 'incident_id'),
        db.Index('ix_incident_events_ts', 'ts'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    incident_id: int = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False, index=True)
    event_type: str = db.Column(db.String(64), nullable=False)
    payload = db.Column(MutableDict.as_mutable(db.JSON().with_variant(JSONB, 'postgresql')), nullable=True)
    ts = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def payload_json(self) -> Optional[str]:
        if self.payload is None:
            return None
        return json.dumps(self.payload, ensure_ascii=False)

    @payload_json.setter
    def payload_json(self, value: Optional[Any]) -> None:
        if value is None:
            self.payload = None
        elif isinstance(value, dict):
            self.payload = value
        elif isinstance(value, str):
            try:
                self.payload = json.loads(value) if value else {}
            except Exception:
                self.payload = {}
        else:
            self.payload = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'incident_id': self.incident_id,
            'event_type': self.event_type,
            'payload': self.payload or {},
            'ts': self.ts.isoformat() if self.ts else None,
        }


class IncidentAssignment(db.Model):
    """Назначение наряда на инцидент.

    Записывает, какой наряд (shift) назначен на инцидент и в какие моменты
    времени наряд принял вызов, выехал, прибыл и завершил работу. Это
    позволяет строить отчёты о времени реакции и соблюдать SLA.
    """

    __tablename__ = 'incident_assignments'
    __table_args__ = (
        db.Index('ix_incident_assignments_incident', 'incident_id'),
        db.Index('ix_incident_assignments_shift', 'shift_id'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    incident_id: int = db.Column(db.Integer, db.ForeignKey('incidents.id'), nullable=False, index=True)
    shift_id: int = db.Column(db.Integer, db.ForeignKey('duty_shifts.id'), nullable=False, index=True)

    assigned_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    enroute_at = db.Column(db.DateTime, nullable=True)
    on_scene_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    shift = db.relationship('DutyShift', lazy='selectin')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'incident_id': self.incident_id,
            'shift_id': self.shift_id,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'enroute_at': self.enroute_at.isoformat() if self.enroute_at else None,
            'on_scene_at': self.on_scene_at.isoformat() if self.on_scene_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
        }

class Zone(db.Model):
    """Модель зоны. Содержит описание, цвет, иконку и геометрию."""

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(32), nullable=False)
    icon = db.Column(db.String(64), nullable=True)
    geometry = db.Column(db.Text, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """
        Преобразовать зону в словарь для сериализации в JSON.

        Геометрия хранится как строка; при выводе пытаемся
        разобрать её в JSON. Если чтение не удалось, geometry = None.
        """
        try:
            geom = json.loads(self.geometry)
        except Exception:
            geom = None
        return {
            "id": self.id,
            "description": self.description,
            "color": self.color,
            "icon": self.icon,
            "geometry": geom,
        }


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------

class ChatDialog(db.Model):
    """Диалог чата с пользователем.

    Хранит агрегированное состояние переписки: статус и счётчики
    непрочитанных сообщений. Один диалог соответствует одному
    Telegram `user_id`.
    """

    __tablename__ = 'chat_dialogs'
    __table_args__ = (
        db.Index('ix_chat_dialogs_status_last', 'status', 'last_message_at'),
    )

    user_id: str = db.Column(db.String(64), primary_key=True)
    # Статус диалога: 'new' | 'in_progress' | 'closed'
    status: str = db.Column(db.String(16), nullable=False, default='new')
    # Непрочитанные сообщения для администратора (от пользователя)
    unread_for_admin: int = db.Column(db.Integer, nullable=False, default=0)
    # Непрочитанные сообщения для пользователя (от админа)
    unread_for_user: int = db.Column(db.Integer, nullable=False, default=0)
    # Время последнего сообщения в диалоге
    last_message_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # --- Telegram-профиль пользователя (для отображения ников в админ-чате) ---
    # username без @ (как приходит из Telegram), может быть None
    tg_username: str = db.Column(db.String(64), nullable=True)
    tg_first_name: str = db.Column(db.String(128), nullable=True)
    tg_last_name: str = db.Column(db.String(128), nullable=True)
    # Человекочитаемое имя (например "@user" или "Иван Петров")
    display_name: str = db.Column(db.String(256), nullable=True)

    # Последнее уведомленное пользователю сообщение от админа (id).
    # Нужно, чтобы бот мог надёжно присылать уведомления без повторов.
    last_notified_admin_msg_id: int = db.Column(db.Integer, nullable=False, default=0)

    # Последнее просмотренное пользователем сообщение от админа (id).
    # Нужно для корректного счётчика непрочитанных в боте.
    last_seen_admin_msg_id: int = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'status': self.status,
            'unread_for_admin': self.unread_for_admin,
            'unread_for_user': self.unread_for_user,
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'tg_username': self.tg_username,
            'tg_first_name': self.tg_first_name,
            'tg_last_name': self.tg_last_name,
            'display_name': self.display_name,
            'last_notified_admin_msg_id': int(self.last_notified_admin_msg_id or 0),
            'last_seen_admin_msg_id': int(getattr(self, 'last_seen_admin_msg_id', 0) or 0),
        }


class ChatMessage(db.Model):
    """Сообщение чата между пользователем и администратором.

    Каждое сообщение принадлежит идентификатору пользователя бота (user_id).
    sender указывает, кто отправил сообщение: 'user' (пользователь) или 'admin'.
    text содержит текстовое содержимое. created_at — временная метка создания.
    """

    __tablename__ = 'chat_messages'
    __table_args__ = (
        db.Index('ix_chat_messages_user_created', 'user_id', 'created_at'),
    )
    id: int = db.Column(db.Integer, primary_key=True)
    user_id: str = db.Column(db.String(64), nullable=False)
    sender: str = db.Column(db.String(16), nullable=False)
    text: str = db.Column(db.Text, nullable=False)
    # Признак того, что сообщение пользователя прочитано администратором
    is_read: bool = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать сообщение в словарь."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'sender': self.sender,
            'text': self.text,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

# ---------------------------------------------------------------------------
# DUTY / GEO-TRACKING (Наряды)
# ---------------------------------------------------------------------------

class DutyShift(db.Model):
    """Смена (несение службы) для наряда/пользователя Telegram."""

    __tablename__ = 'duty_shifts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(32), index=True, nullable=False)   # Telegram user id
    unit_label = db.Column(db.String(64), nullable=True)             # номер наряда / позывной

    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ended_at = db.Column(db.DateTime, nullable=True, index=True)

    start_lat = db.Column(db.Float, nullable=True)
    start_lon = db.Column(db.Float, nullable=True)
    end_lat = db.Column(db.Float, nullable=True)
    end_lon = db.Column(db.Float, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'unit_label': self.unit_label,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'start': {'lat': self.start_lat, 'lon': self.start_lon},
            'end': {'lat': self.end_lat, 'lon': self.end_lon},
        }


class DutyEvent(db.Model):
    """Журнал событий смены."""

    __tablename__ = 'duty_events'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(32), index=True, nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('duty_shifts.id'), nullable=True, index=True)

    ts = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    event_type = db.Column(db.String(64), index=True, nullable=False)
    actor = db.Column(db.String(16), default='system')  # user/admin/system
    payload = db.Column(MutableDict.as_mutable(db.JSON().with_variant(JSONB, 'postgresql')), nullable=True)

    @property
    def payload_json(self) -> Optional[str]:
        if self.payload is None:
            return None
        return json.dumps(self.payload, ensure_ascii=False)

    @payload_json.setter
    def payload_json(self, value: Optional[Any]) -> None:
        if value is None:
            self.payload = None
        elif isinstance(value, dict):
            self.payload = value
        elif isinstance(value, str):
            try:
                self.payload = json.loads(value) if value else {}
            except Exception:
                self.payload = {}
        else:
            self.payload = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'shift_id': self.shift_id,
            'ts': self.ts.isoformat() if self.ts else None,
            'event_type': self.event_type,
            'actor': self.actor,
            'payload': self.payload or {},
        }


class TrackingSession(db.Model):
    """Сессия live-трекинга (Telegram live location)."""

    __tablename__ = 'tracking_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(32), index=True, nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('duty_shifts.id'), nullable=True, index=True)

    message_id = db.Column(db.Integer, nullable=True, index=True)  # Telegram message id live-location
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ended_at = db.Column(db.DateTime, nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True)

    last_lat = db.Column(db.Float, nullable=True)
    last_lon = db.Column(db.Float, nullable=True)
    last_at = db.Column(db.DateTime, nullable=True)

    snapshot_path = db.Column(db.String(255), nullable=True)
    summary_json = db.Column(db.Text, nullable=True)

    def summary(self) -> Dict[str, Any]:
        try:
            return json.loads(self.summary_json or '{}') if self.summary_json else {}
        except Exception:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'shift_id': self.shift_id,
            'message_id': self.message_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'is_active': bool(self.is_active),
            'last': {'lat': self.last_lat, 'lon': self.last_lon, 'ts': self.last_at.isoformat() if self.last_at else None},
            'snapshot_path': self.snapshot_path,
            'summary': self.summary(),
        }


class TrackingPoint(db.Model):
    """Точка трека (live или одноразовая отбивка)."""

    __tablename__ = 'tracking_points'

    __table_args__ = (
        UniqueConstraint('session_id', 'ts', 'kind', name='uq_tracking_points_session_ts_kind'),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('tracking_sessions.id'), nullable=True, index=True)
    user_id = db.Column(db.String(32), index=True, nullable=False)

    ts = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    accuracy_m = db.Column(db.Float, nullable=True)
    kind = db.Column(db.String(16), default='live')  # live/checkin/location
    raw_json = db.Column(db.Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'ts': self.ts.isoformat() if self.ts else None,
            'lat': self.lat,
            'lon': self.lon,
            'accuracy_m': self.accuracy_m,
            'kind': self.kind,
        }


class TrackingStop(db.Model):
    """Стоянка (когда наряд находился в радиусе R)."""

    __tablename__ = 'tracking_stops'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('tracking_sessions.id'), nullable=False, index=True)

    start_ts = db.Column(db.DateTime, nullable=True, index=True)
    end_ts = db.Column(db.DateTime, nullable=True, index=True)
    center_lat = db.Column(db.Float, nullable=True)
    center_lon = db.Column(db.Float, nullable=True)
    duration_sec = db.Column(db.Integer, default=0)
    radius_m = db.Column(db.Integer, default=10)
    points_count = db.Column(db.Integer, default=0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'start_ts': self.start_ts.isoformat() if self.start_ts else None,
            'end_ts': self.end_ts.isoformat() if self.end_ts else None,
            'center_lat': self.center_lat,
            'center_lon': self.center_lon,
            'duration_sec': self.duration_sec,
            'radius_m': self.radius_m,
            'points_count': self.points_count,
        }


class BreakRequest(db.Model):
    """Запрос на обед/перерыв."""

    __tablename__ = 'break_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(32), index=True, nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('duty_shifts.id'), nullable=True, index=True)

    requested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    duration_min = db.Column(db.Integer, default=30)

    status = db.Column(db.String(16), default='requested', index=True)  # requested/started/ended/rejected
    approved_by = db.Column(db.String(64), nullable=True)

    started_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)

    due_notified = db.Column(db.Boolean, default=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'shift_id': self.shift_id,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'duration_min': self.duration_min,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ends_at': self.ends_at.isoformat() if self.ends_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'due_notified': bool(self.due_notified),
        }



class SosAlert(db.Model):
    """SOS-сигнал от наряда (экстренная ситуация).

    Создаётся ботом по нажатию кнопки 🆘 SOS. Админ видит alert в реальном времени
    и может подтвердить (ACK) или закрыть.
    """

    __tablename__ = 'sos_alerts'
    __table_args__ = (
        db.Index('ix_sos_alerts_user_status', 'user_id', 'status'),
        db.Index('ix_sos_alerts_created_at', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(32), index=True, nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('duty_shifts.id'), nullable=True, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('tracking_sessions.id'), nullable=True, index=True)

    unit_label = db.Column(db.String(64), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    status = db.Column(db.String(16), default='open', index=True)  # open/acked/closed

    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    accuracy_m = db.Column(db.Float, nullable=True)

    note = db.Column(db.String(256), nullable=True)

    acked_at = db.Column(db.DateTime, nullable=True)
    acked_by = db.Column(db.String(64), nullable=True)

    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by = db.Column(db.String(64), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'shift_id': self.shift_id,
            'session_id': self.session_id,
            'unit_label': self.unit_label,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'status': self.status,
            'lat': self.lat,
            'lon': self.lon,
            'accuracy_m': self.accuracy_m,
            'note': self.note,
            'acked_at': self.acked_at.isoformat() if self.acked_at else None,
            'acked_by': self.acked_by,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'closed_by': self.closed_by,
        }


class DutyNotification(db.Model):
    """Уведомление для наряда, которое бот заберёт polling-ом."""

    __tablename__ = 'duty_notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(32), index=True, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    kind = db.Column(db.String(32), index=True, nullable=False)
    text = db.Column(db.String(4096), nullable=False)
    payload = db.Column(MutableDict.as_mutable(db.JSON().with_variant(JSONB, 'postgresql')), nullable=True)

    acked = db.Column(db.Boolean, default=False, index=True)
    acked_at = db.Column(db.DateTime, nullable=True)

    @property
    def payload_json(self) -> Optional[str]:
        if self.payload is None:
            return None
        return json.dumps(self.payload, ensure_ascii=False)

    @payload_json.setter
    def payload_json(self, value: Optional[Any]) -> None:
        if value is None:
            self.payload = None
        elif isinstance(value, dict):
            self.payload = value
        elif isinstance(value, str):
            try:
                self.payload = json.loads(value) if value else {}
            except Exception:
                self.payload = {}
        else:
            self.payload = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'kind': self.kind,
            'text': self.text,
            'payload': self.payload or {},
        }


# ---------------------------------------------------------------------------
# Tracker devices (Android) — pairing codes + device tokens
# ---------------------------------------------------------------------------

class TrackerPairCode(db.Model):
    """Одноразовый код привязки устройства (храним только SHA256)."""

    __tablename__ = 'tracker_pair_codes'

    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True, index=True)

    # необязательная подпись коду (например, "Наряд 12", "Телефон #3")
    label = db.Column(db.String(128), nullable=True)

    def is_active(self) -> bool:
        return (self.used_at is None) and (self.expires_at > datetime.now(timezone.utc).replace(tzinfo=None))


class TrackerBootstrapToken(db.Model):
    """Одноразовый bootstrap-токен для Android.

    Используется так:
      1) Telegram-бот запрашивает токен у сервера (BOT_API_KEY + Telegram user_id).
      2) Бот присылает deep-link dutytracker://bootstrap?base_url=...&token=...
      3) Приложение по token забирает конфиг и автоматически делает pairing.
    """

    __tablename__ = 'tracker_bootstrap_tokens'

    id = db.Column(db.Integer, primary_key=True)

    token_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)
    pair_code = db.Column(db.String(6), nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True, index=True)

    tg_user_id = db.Column(db.String(64), nullable=True, index=True)
    label = db.Column(db.String(128), nullable=True)

    # base_url, который бот передаст приложению (LAN/VPN адрес)
    base_url = db.Column(db.String(256), nullable=True)

    def is_expired(self) -> bool:
        try:
            _now = datetime.now(timezone.utc).replace(tzinfo=None)
            return _now >= (self.expires_at or _now)
        except Exception:
            return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "tg_user_id": self.tg_user_id,
            "label": self.label,
            "base_url": self.base_url,
        }


# ---------------------------------------------------------------------------
# Service access ("Служба" по заявке)
# ---------------------------------------------------------------------------



class TrackerConnectRequest(db.Model):
    """Заявка на привязку Android DutyTracker.

    Сценарий:
      1) Пользователь в Telegram (с ролью officer/admin) нажимает "Подключить DutyTracker".
      2) Бот создаёт заявку со статусом pending.
      3) Админ на сайте подтверждает (approve) и сервер выпускает bootstrap-токен.
      4) Сервер (best-effort) отправляет пользователю кнопку deep-link в Telegram.

    Важно:
      - Токен одноразовый и хранится только в виде hash (в TrackerBootstrapToken).
      - Если пользователь пропустил сообщение, бот может "довыдать" новый токен через status?issue=1.
    """

    __tablename__ = "tracker_connect_requests"

    id = db.Column(db.Integer, primary_key=True)

    tg_user_id = db.Column(db.String(64), unique=True, index=True, nullable=False)
    status = db.Column(db.String(16), default="pending", index=True, nullable=False)

    note = db.Column(db.String(256), nullable=True)
    base_url = db.Column(db.String(256), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), index=True)

    approved_at = db.Column(db.DateTime, nullable=True, index=True)
    denied_at = db.Column(db.DateTime, nullable=True, index=True)

    # Связь с последним выпущенным bootstrap токеном (hash).
    last_bootstrap_token_hash = db.Column(db.String(64), nullable=True, index=True)
    last_pair_code = db.Column(db.String(6), nullable=True)

    last_issued_at = db.Column(db.DateTime, nullable=True)
    last_sent_at = db.Column(db.DateTime, nullable=True)
    last_sent_via = db.Column(db.String(16), nullable=True)  # auto|pull
    last_send_error = db.Column(db.String(512), nullable=True)

    def to_dict(self) -> dict:
        return {
            "tg_user_id": self.tg_user_id,
            "status": self.status,
            "note": self.note,
            "base_url": self.base_url,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "approved_at": self.approved_at.isoformat() + "Z" if self.approved_at else None,
            "denied_at": self.denied_at.isoformat() + "Z" if self.denied_at else None,
            "last_bootstrap_token_hash": self.last_bootstrap_token_hash,
            "last_pair_code": self.last_pair_code,
            "last_issued_at": self.last_issued_at.isoformat() + "Z" if self.last_issued_at else None,
            "last_sent_at": self.last_sent_at.isoformat() + "Z" if self.last_sent_at else None,
            "last_sent_via": self.last_sent_via,
            "last_send_error": self.last_send_error,
        }


class ServiceAccess(db.Model):
    """Статус доступа пользователя Telegram к служебному разделу.

    Модель хранит одну строку на tg_user_id.

    Статусы:
      - guest: нет доступа
      - pending: заявка подана, ожидает решения
      - officer: доступ выдан
      - admin: служебный доступ по умолчанию (можно использовать для внутренних аккаунтов)
      - denied: заявка отклонена (по UI можно показывать отдельно от guest)
    """

    __tablename__ = "service_access"

    id = db.Column(db.Integer, primary_key=True)

    tg_user_id = db.Column(db.String(64), unique=True, index=True, nullable=False)
    status = db.Column(db.String(16), index=True, nullable=False, default="guest")

    requested_at = db.Column(db.DateTime, nullable=True, index=True)
    decided_at = db.Column(db.DateTime, nullable=True, index=True)
    decided_by = db.Column(db.String(128), nullable=True)

    note = db.Column(db.String(256), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def normalize_status(self) -> str:
        st = (self.status or "").strip().lower()
        if st not in {"guest", "pending", "officer", "admin", "denied"}:
            return "guest"
        return st

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tg_user_id": self.tg_user_id,
            "status": self.normalize_status(),
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by,
            "note": self.note,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TrackerDevice(db.Model):
    """Устройство (телефон), привязанное через pairing код."""

    __tablename__ = 'tracker_devices'

    id = db.Column(db.Integer, primary_key=True)

    # короткий публичный id, который можно показывать в UI (до 32 символов)
    public_id = db.Column(db.String(32), unique=True, index=True, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    last_seen_at = db.Column(db.DateTime, nullable=True, index=True)

    # авторизация устройства: храним только SHA256 токена
    token_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)

    is_revoked = db.Column(db.Boolean, default=False, index=True)

    # как это устройство будет отображаться в админке
    label = db.Column(db.String(128), nullable=True)

    # профиль (ФИО, номер наряда, подразделение и т.д.) — JSON строкой
    profile_json = db.Column(db.Text, nullable=True)

    # удобная связка с существующими сущностями (user_id в Duty/Tracking)
    user_id = db.Column(db.String(32), index=True, nullable=False)

    def profile(self) -> Dict[str, Any]:
        try:
            return json.loads(self.profile_json or '{}') or {}
        except Exception:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать устройство в словарь для JSON-ответов."""
        return {
            'id': self.id,
            'public_id': self.public_id,
            'user_id': self.user_id,
            'label': self.label,
            'is_revoked': bool(self.is_revoked),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'profile': self.profile(),
        }


class TrackerDeviceHealth(db.Model):
    """Последний health-пакет от Android устройства.

    Специально отдельная таблица, чтобы не требовать миграций при
    добавлении новых полей (app.db часто уже существует у пользователя).
    Храним только *последнее* состояние на устройство.
    """

    __tablename__ = 'tracker_device_health'

    device_id = db.Column(db.String(32), primary_key=True)  # TrackerDevice.public_id
    user_id = db.Column(db.String(32), index=True, nullable=False)

    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    battery_pct = db.Column(db.Integer, nullable=True)
    is_charging = db.Column(db.Boolean, nullable=True)

    net = db.Column(db.String(16), nullable=True)  # wifi/cell/none/unknown
    gps = db.Column(db.String(16), nullable=True)  # ok/off/denied/unknown

    accuracy_m = db.Column(db.Float, nullable=True)
    queue_size = db.Column(db.Integer, nullable=True)
    tracking_on = db.Column(db.Boolean, nullable=True)

    last_send_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.String(256), nullable=True)

    app_version = db.Column(db.String(32), nullable=True)
    device_model = db.Column(db.String(64), nullable=True)
    os_version = db.Column(db.String(32), nullable=True)

    extra_json = db.Column(db.Text, nullable=True)

    def extra(self) -> Dict[str, Any]:
        try:
            return json.loads(self.extra_json or '{}') or {}
        except Exception:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'device_id': self.device_id,
            'user_id': self.user_id,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'battery_pct': self.battery_pct,
            'is_charging': self.is_charging,
            'net': self.net,
            'gps': self.gps,
            'accuracy_m': self.accuracy_m,
            'queue_size': self.queue_size,
            'tracking_on': self.tracking_on,
            'last_send_at': self.last_send_at.isoformat() if self.last_send_at else None,
            'last_error': self.last_error,
            'app_version': self.app_version,
            'device_model': self.device_model,
            'os_version': self.os_version,
            'extra': self.extra(),
        }


class TrackerDeviceHealthLog(db.Model):
    """История health-пакетов (лог).

    Таблица нужна для "drill-down" на странице устройства:
    диспетчер может посмотреть, как менялась батарея/сеть/GPS/очередь.

    В отличие от TrackerDeviceHealth, где хранится только *последнее* состояние,
    здесь копим записи (в разумном режиме — раз в N секунд).
    """

    __tablename__ = 'tracker_device_health_log'

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(db.String(32), index=True, nullable=False)  # TrackerDevice.public_id
    user_id = db.Column(db.String(32), index=True, nullable=False)

    ts = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    battery_pct = db.Column(db.Integer, nullable=True)
    is_charging = db.Column(db.Boolean, nullable=True)

    net = db.Column(db.String(16), nullable=True)
    gps = db.Column(db.String(16), nullable=True)

    accuracy_m = db.Column(db.Float, nullable=True)
    queue_size = db.Column(db.Integer, nullable=True)
    tracking_on = db.Column(db.Boolean, nullable=True)

    last_send_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.String(256), nullable=True)

    app_version = db.Column(db.String(32), nullable=True)
    device_model = db.Column(db.String(64), nullable=True)
    os_version = db.Column(db.String(32), nullable=True)

    extra_json = db.Column(db.Text, nullable=True)

    def extra(self) -> Dict[str, Any]:
        try:
            return json.loads(self.extra_json or '{}') or {}
        except Exception:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'device_id': self.device_id,
            'user_id': self.user_id,
            'ts': self.ts.isoformat() if self.ts else None,
            'battery_pct': self.battery_pct,
            'is_charging': self.is_charging,
            'net': self.net,
            'gps': self.gps,
            'accuracy_m': self.accuracy_m,
            'queue_size': self.queue_size,
            'tracking_on': self.tracking_on,
            'last_send_at': self.last_send_at.isoformat() if self.last_send_at else None,
            'last_error': self.last_error,
            'app_version': self.app_version,
            'device_model': self.device_model,
            'os_version': self.os_version,
            'extra': self.extra(),
        }


class TrackerFingerprintSample(db.Model):
    """Снимок радио-отпечатка (Wi‑Fi + Cell) от устройства.

    Цель: накопить данные для indoor/low-GPS локализации без маячков.

    Сейчас это только сбор и хранение. "Локализация по отпечатку" будет
    реализована отдельным этапом (потребует индекс/поиск похожести).
    """

    __tablename__ = 'tracker_fingerprint_samples'
    __table_args__ = (
        db.Index('ix_tracker_fp_device_ts', 'device_id', 'ts'),
    )

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(db.String(32), index=True, nullable=False)  # TrackerDevice.public_id
    user_id = db.Column(db.String(32), index=True, nullable=False)

    ts = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # опционально: если есть хорошая координата в момент снятия отпечатка
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    accuracy_m = db.Column(db.Float, nullable=True)

    # Wi‑Fi scan results (list of dicts)
    wifi_json = db.Column(db.Text, nullable=True)
    # Cell towers (list of dicts)
    cell_json = db.Column(db.Text, nullable=True)

    # Доп. контекст (режим трекинга, purpose=train|locate, etc.)
    meta_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def wifi(self) -> list[dict]:
        try:
            return json.loads(self.wifi_json or '[]') or []
        except Exception:
            return []

    def cell(self) -> list[dict]:
        try:
            return json.loads(self.cell_json or '[]') or []
        except Exception:
            return []

    def meta(self) -> dict:
        try:
            return json.loads(self.meta_json or '{}') or {}
        except Exception:
            return {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'device_id': self.device_id,
            'user_id': self.user_id,
            'ts': self.ts.isoformat() if self.ts else None,
            'lat': self.lat,
            'lon': self.lon,
            'accuracy_m': self.accuracy_m,
            'wifi_count': len(self.wifi()),
            'cell_count': len(self.cell()),
            'meta': self.meta(),
        }




class TrackerRadioTile(db.Model):
    """Агрегированная "radio map" плитка (общая для всех устройств).

    Используется для indoor-позиционирования без маячков: обучаемся на
    отпечатках с хорошим GNSS и потом по Wi‑Fi/Cell выбираем наиболее
    похожую плитку.
    """

    __tablename__ = 'tracker_radio_tiles'

    # Простой grid-id: int(lat*1000) + '_' + int(lon*1000)
    tile_id = db.Column(db.String(64), primary_key=True)

    center_lat = db.Column(db.Float, nullable=False)
    center_lon = db.Column(db.Float, nullable=False)

    samples_count = db.Column(db.Integer, default=0)
    ap_count = db.Column(db.Integer, default=0)
    cell_count = db.Column(db.Integer, default=0)

    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class TrackerRadioAPStat(db.Model):
    """Статистика по Wi‑Fi AP в пределах плитки."""

    __tablename__ = 'tracker_radio_ap_stats'
    __table_args__ = (
        db.UniqueConstraint('tile_id', 'bssid_hash', name='uq_radio_ap_tile_bssid'),
        db.Index('ix_radio_ap_bssid', 'bssid_hash'),
        db.Index('ix_radio_ap_tile', 'tile_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tile_id = db.Column(db.String(64), index=True, nullable=False)
    bssid_hash = db.Column(db.String(64), index=True, nullable=False)

    count = db.Column(db.Integer, default=0)
    rssi_mean = db.Column(db.Float, nullable=True)
    rssi_m2 = db.Column(db.Float, nullable=True)  # Welford M2 for variance

    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def var(self) -> Optional[float]:
        try:
            if (self.count or 0) >= 2 and self.rssi_m2 is not None:
                return float(self.rssi_m2) / float(max(1, (self.count or 0) - 1))
        except Exception:
            pass
        return None


class TrackerRadioCellStat(db.Model):
    """Статистика по Cell towers (клетка/сектор) в пределах плитки."""

    __tablename__ = 'tracker_radio_cell_stats'
    __table_args__ = (
        db.UniqueConstraint('tile_id', 'cell_key_hash', name='uq_radio_cell_tile_key'),
        db.Index('ix_radio_cell_key', 'cell_key_hash'),
        db.Index('ix_radio_cell_tile', 'tile_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tile_id = db.Column(db.String(64), index=True, nullable=False)
    cell_key_hash = db.Column(db.String(64), index=True, nullable=False)

    count = db.Column(db.Integer, default=0)
    dbm_mean = db.Column(db.Float, nullable=True)
    dbm_m2 = db.Column(db.Float, nullable=True)

    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def var(self) -> Optional[float]:
        try:
            if (self.count or 0) >= 2 and self.dbm_m2 is not None:
                return float(self.dbm_m2) / float(max(1, (self.count or 0) - 1))
        except Exception:
            pass
        return None

class TrackerAlert(db.Model):
    """Системный алёрт по устройству/наряду.

    Нужен для диспетчерского контроля: stale, low battery, gps off, queue growing и т.д.
    Алёрты создаются автоматическим чекером и транслируются в UI через WebSocket.
    """

    __tablename__ = 'tracker_alerts'
    __table_args__ = (
        db.Index('ix_tracker_alerts_active', 'is_active', 'kind'),
        db.Index('ix_tracker_alerts_device_kind', 'device_id', 'kind'),
        db.Index('ix_tracker_alerts_user_kind', 'user_id', 'kind'),
    )

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(db.String(32), index=True, nullable=True)  # TrackerDevice.public_id
    user_id = db.Column(db.String(32), index=True, nullable=True)

    kind = db.Column(db.String(32), index=True, nullable=False)       # stale_points, stale_health, low_battery...
    severity = db.Column(db.String(16), default='warn', index=True)   # info/warn/crit

    message = db.Column(db.String(256), nullable=True)
    payload = db.Column(MutableDict.as_mutable(db.JSON().with_variant(JSONB, 'postgresql')), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    is_active = db.Column(db.Boolean, default=True, index=True)

    acked_at = db.Column(db.DateTime, nullable=True)
    acked_by = db.Column(db.String(64), nullable=True)

    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by = db.Column(db.String(64), nullable=True)

    @property
    def payload_json(self) -> Optional[str]:
        if self.payload is None:
            return None
        return json.dumps(self.payload, ensure_ascii=False)

    @payload_json.setter
    def payload_json(self, value: Optional[Any]) -> None:
        if value is None:
            self.payload = None
        elif isinstance(value, dict):
            self.payload = value
        elif isinstance(value, str):
            try:
                self.payload = json.loads(value) if value else {}
            except Exception:
                self.payload = {}
        else:
            self.payload = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'device_id': self.device_id,
            'user_id': self.user_id,
            'kind': self.kind,
            'severity': self.severity,
            'message': self.message,
            'payload': self.payload or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active,
            'acked_at': self.acked_at.isoformat() if self.acked_at else None,
            'acked_by': self.acked_by,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'closed_by': self.closed_by,
        }



class TrackerAlertNotifyLog(db.Model):
    """Лог Telegram-уведомлений по алёртам трекера.

    Нужен для троттлинга (чтобы не спамить одним и тем же алёртом каждые N секунд),
    а также для аудита, что именно и когда было отправлено диспетчеру.
    """

    __tablename__ = 'tracker_alert_notify_log'
    __table_args__ = (
        db.Index('ix_tracker_alert_notify_device_kind', 'device_id', 'kind'),
        db.Index('ix_tracker_alert_notify_sent_at', 'sent_at'),
    )

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(db.String(32), index=True, nullable=True)
    user_id = db.Column(db.String(32), index=True, nullable=True)

    kind = db.Column(db.String(32), index=True, nullable=False)
    severity = db.Column(db.String(16), index=True, nullable=True)

    # кому отправили (Telegram chat_id / user_id)
    sent_to = db.Column(db.String(64), index=True, nullable=False)

    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # короткий "отпечаток" текста, чтобы понимать что именно было отправлено
    digest = db.Column(db.String(64), nullable=True)



class TrackerAdminAudit(db.Model):
    """Аудит действий диспетчера/админа по трекеру."""

    __tablename__ = 'tracker_admin_audit'
    __table_args__ = (db.Index('ix_tracker_audit_ts', 'ts'),)

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    actor = db.Column(db.String(64), nullable=True)   # кто сделал действие (логин/имя)
    action = db.Column(db.String(64), nullable=False) # REVOKE_DEVICE, ACK_ALERT, EXPORT_POINTS...

    device_id = db.Column(db.String(32), nullable=True)
    user_id = db.Column(db.String(32), nullable=True)

    payload = db.Column(MutableDict.as_mutable(db.JSON().with_variant(JSONB, 'postgresql')), nullable=True)

    @property
    def payload_json(self) -> Optional[str]:
        if self.payload is None:
            return None
        return json.dumps(self.payload, ensure_ascii=False)

    @payload_json.setter
    def payload_json(self, value: Optional[Any]) -> None:
        if value is None:
            self.payload = None
        elif isinstance(value, dict):
            self.payload = value
        elif isinstance(value, str):
            try:
                self.payload = json.loads(value) if value else {}
            except Exception:
                self.payload = {}
        else:
            self.payload = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'ts': self.ts.isoformat() if self.ts else None,
            'actor': self.actor,
            'action': self.action,
            'device_id': self.device_id,
            'user_id': self.user_id,
            'payload': self.payload or {},
        }



# ---------------------------------------------------------------------------
# Общий аудит админских действий (security/ops)
# ---------------------------------------------------------------------------

class AdminAuditLog(db.Model):
    """Общий аудит действий администраторов.

    Используется для расследования инцидентов и трассировки действий
    (логин/логаут, модификации чата, опасные операции офлайна и т.п.).
    """

    __tablename__ = 'admin_audit_log'
    __table_args__ = (
        db.Index('ix_admin_audit_ts', 'ts'),
        db.Index('ix_admin_audit_actor', 'actor'),
        db.Index('ix_admin_audit_action', 'action'),
    )

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    actor = db.Column(db.String(64), nullable=True)
    role = db.Column(db.String(16), nullable=True)

    ip = db.Column(db.String(64), nullable=True)
    method = db.Column(db.String(8), nullable=True)
    path = db.Column(db.String(255), nullable=True)

    action = db.Column(db.String(64), nullable=False)
    payload = db.Column(MutableDict.as_mutable(db.JSON().with_variant(JSONB, 'postgresql')), nullable=True)

    @property
    def payload_json(self) -> Optional[str]:
        if self.payload is None:
            return None
        return json.dumps(self.payload, ensure_ascii=False)

    @payload_json.setter
    def payload_json(self, value: Optional[Any]) -> None:
        if value is None:
            self.payload = None
        elif isinstance(value, dict):
            self.payload = value
        elif isinstance(value, str):
            try:
                self.payload = json.loads(value) if value else {}
            except Exception:
                self.payload = {}
        else:
            self.payload = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'ts': self.ts.isoformat() if self.ts else None,
            'actor': self.actor,
            'role': self.role,
            'ip': self.ip,
            'method': self.method,
            'path': self.path,
            'action': self.action,
            'payload': self.payload or {},
        }
