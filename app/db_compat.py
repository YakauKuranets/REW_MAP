"""DB schema compatibility helpers (SQLite).

Причина:
  Старые SQLite базы (app.db) не обновляются автоматически после изменения моделей.
  Flask-SQLAlchemy `db.create_all()` не делает ALTER TABLE, поэтому новые поля
  (например, zone_id) отсутствуют в уже созданных таблицах.

Задача:
  Мягко "подлечить" существующую SQLite базу: добавить недостающие колонки,
  чтобы приложение не падало на JOIN/INSERT.

Ограничения:
  - Для SQLite добавляем только колонки (ALTER TABLE ... ADD COLUMN). Это не добавит
    FK-ограничения, но для нашей логики (JOIN по zone_id) этого достаточно.
  - Для других СУБД этот модуль ничего не делает (в проде используйте миграции).
"""

from __future__ import annotations

from typing import Iterable, Tuple

from sqlalchemy import text

from .extensions import db


def _is_sqlite() -> bool:
    try:
        return db.engine.url.get_backend_name() == "sqlite"
    except Exception:
        return False


def _sqlite_column_names(table: str) -> set[str]:
    """Возвращает набор имён колонок для таблицы SQLite.

    PRAGMA table_info возвращает строки с полями: cid, name, type, notnull, dflt_value, pk.
    """
    rows = db.session.execute(text(f"PRAGMA table_info({table})")).all()
    if not rows:
        return set()
    names: set[str] = set()
    for r in rows:
        try:
            # SQLAlchemy Row
            names.add(r._mapping.get("name"))  # type: ignore[attr-defined]
        except Exception:
            # fallback по индексу
            try:
                names.add(r[1])
            except Exception:
                pass
    return {n for n in names if n}


def ensure_sqlite_columns(columns: Iterable[Tuple[str, str, str]]) -> bool:
    """Добавляет недостающие колонки в SQLite.

    Args:
        columns: итератор кортежей (table, column_name, column_sql_decl)
                 пример: ("addresses", "zone_id", "zone_id INTEGER")

    Returns:
        True если хотя бы одна колонка была добавлена.
    """
    if not _is_sqlite():
        return False

    added_any = False
    try:
        for table, col, decl in columns:
            try:
                existing = _sqlite_column_names(table)
                if existing and col not in existing:
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {decl}"))
                    added_any = True
            except Exception:
                # не даём приложению упасть из-за попытки миграции
                db.session.rollback()
        if added_any:
            db.session.commit()
        return added_any
    except Exception:
        db.session.rollback()
        return False


def ensure_sqlite_schema_minimal() -> bool:
    """Минимальная авто-миграция для совместимости старых баз."""
    return ensure_sqlite_columns(
        [
            ("addresses", "zone_id", "zone_id INTEGER"),
            ("pending_markers", "zone_id", "zone_id INTEGER"),
            # Очень старые базы могли не иметь технических колонок для трассировки бота
            ("pending_markers", "user_id", "user_id VARCHAR(64)"),
            ("pending_markers", "message_id", "message_id VARCHAR(64)"),

            # Чат: в старых базах chat_messages мог не иметь признака прочитанности.
            # SQLite хранит bool как INTEGER 0/1.
            ("chat_messages", "is_read", "is_read INTEGER NOT NULL DEFAULT 0"),

            # Диалоги: таблица могла быть создана раньше без счётчиков/статуса.
            ("chat_dialogs", "status", "status VARCHAR(16) NOT NULL DEFAULT 'new'"),
            ("chat_dialogs", "unread_for_admin", "unread_for_admin INTEGER NOT NULL DEFAULT 0"),
            ("chat_dialogs", "unread_for_user", "unread_for_user INTEGER NOT NULL DEFAULT 0"),
            ("chat_dialogs", "last_message_at", "last_message_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),

            # Telegram-профиль в диалоге (нужен, чтобы в админ-чате были не только цифры ID)
            ("chat_dialogs", "tg_username", "tg_username VARCHAR(64)"),
            ("chat_dialogs", "tg_first_name", "tg_first_name VARCHAR(128)"),
            ("chat_dialogs", "tg_last_name", "tg_last_name VARCHAR(128)"),
            ("chat_dialogs", "display_name", "display_name VARCHAR(256)"),
            ("chat_dialogs", "last_notified_admin_msg_id", "last_notified_admin_msg_id INTEGER NOT NULL DEFAULT 0"),
            ("chat_dialogs", "last_seen_admin_msg_id", "last_seen_admin_msg_id INTEGER NOT NULL DEFAULT 0"),
        ]
    )



def ensure_sqlite_unique_indexes() -> None:
    """Create missing UNIQUE indexes for SQLite (best-effort).

    Note: if existing data violates the unique constraint, SQLite will fail to create the index.
    We do NOT crash the app in that case.
    """
    if not _is_sqlite():
        return
    from .extensions import db
    try:
        db.session.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_tracking_points_session_ts_kind ON tracking_points(session_id, ts, kind)")
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

