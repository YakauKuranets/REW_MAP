"""initial schema (explicit DDL, no create_all)

Revision ID: 0001_init
Revises: 
Create Date: 2025-12-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    insp = inspect(conn)
    return table_name in set(insp.get_table_names())


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    insp = inspect(conn)
    try:
        for ix in insp.get_indexes(table_name):
            if ix.get("name") == index_name:
                return True
    except Exception:
        return False
    return False


def upgrade():
    conn = op.get_bind()

    if not _table_exists(conn, 'zone'):
        op.create_table(
            'zone',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('color', sa.String(32), nullable=False),
            sa.Column('icon', sa.String(64), nullable=True),
            sa.Column('geometry', sa.Text(), nullable=False)
        )

    if not _table_exists(conn, 'admin_users'):
        op.create_table(
            'admin_users',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('username', sa.String(64), nullable=False, unique=True),
            sa.Column('password_hash', sa.String(255), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False)
        )

    if not _table_exists(conn, 'addresses'):
        op.create_table(
            'addresses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('lat', sa.Float(), nullable=True),
            sa.Column('lon', sa.Float(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('status', sa.String(64), nullable=True),
            sa.Column('link', sa.String(512), nullable=True),
            sa.Column('category', sa.String(128), nullable=True),
            sa.Column('zone_id', sa.Integer(), sa.ForeignKey('zone.id'), nullable=True),
            sa.Column('photo', sa.String(128), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime())
        )

    if not _table_exists(conn, 'pending_markers'):
        op.create_table(
            'pending_markers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('lat', sa.Float(), nullable=True),
            sa.Column('lon', sa.Float(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('status', sa.String(64), nullable=True),
            sa.Column('link', sa.String(512), nullable=True),
            sa.Column('category', sa.String(128), nullable=True),
            sa.Column('zone_id', sa.Integer(), sa.ForeignKey('zone.id'), nullable=True),
            sa.Column('photo', sa.String(128), nullable=True),
            sa.Column('user_id', sa.String(64), nullable=True),
            sa.Column('message_id', sa.String(64), nullable=True),
            sa.Column('reporter', sa.String(128), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime())
        )

    if not _table_exists(conn, 'pending_history'):
        op.create_table(
            'pending_history',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('pending_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(32), nullable=False),
            sa.Column('timestamp', sa.DateTime()),
            sa.Column('address_id', sa.Integer(), nullable=True)
        )

    if not _table_exists(conn, 'chat_dialogs'):
        op.create_table(
            'chat_dialogs',
            sa.Column('user_id', sa.String(64), primary_key=True),
            sa.Column('status', sa.String(16), nullable=False),
            sa.Column('unread_for_admin', sa.Integer(), nullable=False),
            sa.Column('unread_for_user', sa.Integer(), nullable=False),
            sa.Column('last_message_at', sa.DateTime(), nullable=False),
            sa.Column('tg_username', sa.String(64), nullable=True),
            sa.Column('tg_first_name', sa.String(128), nullable=True),
            sa.Column('tg_last_name', sa.String(128), nullable=True),
            sa.Column('display_name', sa.String(256), nullable=True),
            sa.Column('last_notified_admin_msg_id', sa.Integer(), nullable=False),
            sa.Column('last_seen_admin_msg_id', sa.Integer(), nullable=False)
        )

    if not _table_exists(conn, 'chat_messages'):
        op.create_table(
            'chat_messages',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(64), nullable=False),
            sa.Column('sender', sa.String(16), nullable=False),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('is_read', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime())
        )

    if not _table_exists(conn, 'duty_shifts'):
        op.create_table(
            'duty_shifts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('started_at', sa.DateTime()),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('start_lat', sa.Float(), nullable=True),
            sa.Column('start_lon', sa.Float(), nullable=True),
            sa.Column('end_lat', sa.Float(), nullable=True),
            sa.Column('end_lon', sa.Float(), nullable=True)
        )

    if not _table_exists(conn, 'duty_events'):
        op.create_table(
            'duty_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('shift_id', sa.Integer(), sa.ForeignKey('duty_shifts.id'), nullable=True),
            sa.Column('ts', sa.DateTime()),
            sa.Column('event_type', sa.String(64), nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=True)
        )

    if not _table_exists(conn, 'tracking_sessions'):
        op.create_table(
            'tracking_sessions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('shift_id', sa.Integer(), sa.ForeignKey('duty_shifts.id'), nullable=True),
            sa.Column('started_at', sa.DateTime()),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('last_lat', sa.Float(), nullable=True),
            sa.Column('last_lon', sa.Float(), nullable=True),
            sa.Column('last_at', sa.DateTime(), nullable=True),
            sa.Column('snapshot_path', sa.String(255), nullable=True),
            sa.Column('summary_json', sa.Text(), nullable=True)
        )

    if not _table_exists(conn, 'tracking_points'):
        op.create_table(
            'tracking_points',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('session_id', sa.Integer(), sa.ForeignKey('tracking_sessions.id'), nullable=True),
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('ts', sa.DateTime()),
            sa.Column('lat', sa.Float(), nullable=True),
            sa.Column('lon', sa.Float(), nullable=True),
            sa.Column('accuracy_m', sa.Float(), nullable=True),
            sa.Column('raw_json', sa.Text(), nullable=True),
            sa.UniqueConstraint('session_id', 'ts', 'kind', name='uq_tracking_points_session_ts_kind')
        )

    if not _table_exists(conn, 'tracking_stops'):
        op.create_table(
            'tracking_stops',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('session_id', sa.Integer(), sa.ForeignKey('tracking_sessions.id'), nullable=False),
            sa.Column('start_ts', sa.DateTime(), nullable=True),
            sa.Column('end_ts', sa.DateTime(), nullable=True),
            sa.Column('center_lat', sa.Float(), nullable=True),
            sa.Column('center_lon', sa.Float(), nullable=True),
            sa.Column('duration_sec', sa.Integer()),
            sa.Column('radius_m', sa.Integer()),
            sa.Column('points_count', sa.Integer())
        )

    if not _table_exists(conn, 'break_requests'):
        op.create_table(
            'break_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('shift_id', sa.Integer(), sa.ForeignKey('duty_shifts.id'), nullable=True),
            sa.Column('requested_at', sa.DateTime()),
            sa.Column('duration_min', sa.Integer()),
            sa.Column('approved_by', sa.String(64), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('ends_at', sa.DateTime(), nullable=True),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('due_notified', sa.Boolean())
        )

    if not _table_exists(conn, 'sos_alerts'):
        op.create_table(
            'sos_alerts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('shift_id', sa.Integer(), sa.ForeignKey('duty_shifts.id'), nullable=True),
            sa.Column('session_id', sa.Integer(), sa.ForeignKey('tracking_sessions.id'), nullable=True),
            sa.Column('unit_label', sa.String(64), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('lat', sa.Float(), nullable=True),
            sa.Column('lon', sa.Float(), nullable=True),
            sa.Column('accuracy_m', sa.Float(), nullable=True),
            sa.Column('note', sa.String(256), nullable=True),
            sa.Column('acked_at', sa.DateTime(), nullable=True),
            sa.Column('acked_by', sa.String(64), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('closed_by', sa.String(64), nullable=True)
        )

    if not _table_exists(conn, 'duty_notifications'):
        op.create_table(
            'duty_notifications',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('kind', sa.String(32), nullable=False),
            sa.Column('text', sa.String(4096), nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=True),
            sa.Column('acked', sa.Boolean()),
            sa.Column('acked_at', sa.DateTime(), nullable=True)
        )

    if not _table_exists(conn, 'tracker_pair_codes'):
        op.create_table(
            'tracker_pair_codes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code_hash', sa.String(64), nullable=False, unique=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('label', sa.String(128), nullable=True)
        )

    if not _table_exists(conn, 'tracker_devices'):
        op.create_table(
            'tracker_devices',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('public_id', sa.String(32), nullable=False, unique=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('last_seen_at', sa.DateTime(), nullable=True),
            sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
            sa.Column('is_revoked', sa.Boolean()),
            sa.Column('label', sa.String(128), nullable=True),
            sa.Column('profile_json', sa.Text(), nullable=True),
            sa.Column('user_id', sa.String(32), nullable=False)
        )

    if not _table_exists(conn, 'tracker_device_health'):
        op.create_table(
            'tracker_device_health',
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('updated_at', sa.DateTime()),
            sa.Column('battery_pct', sa.Integer(), nullable=True),
            sa.Column('is_charging', sa.Boolean(), nullable=True),
            sa.Column('accuracy_m', sa.Float(), nullable=True),
            sa.Column('queue_size', sa.Integer(), nullable=True),
            sa.Column('tracking_on', sa.Boolean(), nullable=True),
            sa.Column('last_send_at', sa.DateTime(), nullable=True),
            sa.Column('last_error', sa.String(256), nullable=True),
            sa.Column('app_version', sa.String(32), nullable=True),
            sa.Column('device_model', sa.String(64), nullable=True),
            sa.Column('os_version', sa.String(32), nullable=True),
            sa.Column('extra_json', sa.Text(), nullable=True)
        )

    if not _table_exists(conn, 'tracker_device_health_log'):
        op.create_table(
            'tracker_device_health_log',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(32), nullable=False),
            sa.Column('ts', sa.DateTime()),
            sa.Column('battery_pct', sa.Integer(), nullable=True),
            sa.Column('is_charging', sa.Boolean(), nullable=True),
            sa.Column('net', sa.String(16), nullable=True),
            sa.Column('gps', sa.String(16), nullable=True),
            sa.Column('accuracy_m', sa.Float(), nullable=True),
            sa.Column('queue_size', sa.Integer(), nullable=True),
            sa.Column('tracking_on', sa.Boolean(), nullable=True),
            sa.Column('last_send_at', sa.DateTime(), nullable=True),
            sa.Column('last_error', sa.String(256), nullable=True),
            sa.Column('app_version', sa.String(32), nullable=True),
            sa.Column('device_model', sa.String(64), nullable=True),
            sa.Column('os_version', sa.String(32), nullable=True),
            sa.Column('extra_json', sa.Text(), nullable=True)
        )

    if not _table_exists(conn, 'tracker_alerts'):
        op.create_table(
            'tracker_alerts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.String(32), nullable=True),
            sa.Column('message', sa.String(256), nullable=True),
            sa.Column('payload_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
            sa.Column('is_active', sa.Boolean()),
            sa.Column('acked_at', sa.DateTime(), nullable=True),
            sa.Column('acked_by', sa.String(64), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('closed_by', sa.String(64), nullable=True)
        )

    if not _table_exists(conn, 'tracker_admin_audit'):
        op.create_table(
            'tracker_admin_audit',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('ts', sa.DateTime()),
            sa.Column('actor', sa.String(64)),
            sa.Column('device_id', sa.String(32), nullable=True),
            sa.Column('user_id', sa.String(32), nullable=True),
            sa.Column('payload_json', sa.Text(), nullable=True)
        )


    # single-column indexes (from models index=True)
    if _table_exists(conn, 'duty_shifts') and not _index_exists(conn, 'duty_shifts', 'ix_duty_shifts_started_at'):
        op.create_index('ix_duty_shifts_started_at', 'duty_shifts', ['started_at'])
    if _table_exists(conn, 'duty_shifts') and not _index_exists(conn, 'duty_shifts', 'ix_duty_shifts_ended_at'):
        op.create_index('ix_duty_shifts_ended_at', 'duty_shifts', ['ended_at'])
    if _table_exists(conn, 'duty_events') and not _index_exists(conn, 'duty_events', 'ix_duty_events_user_id'):
        op.create_index('ix_duty_events_user_id', 'duty_events', ['user_id'])
    if _table_exists(conn, 'duty_events') and not _index_exists(conn, 'duty_events', 'ix_duty_events_shift_id'):
        op.create_index('ix_duty_events_shift_id', 'duty_events', ['shift_id'])
    if _table_exists(conn, 'duty_events') and not _index_exists(conn, 'duty_events', 'ix_duty_events_ts'):
        op.create_index('ix_duty_events_ts', 'duty_events', ['ts'])
    if _table_exists(conn, 'duty_events') and not _index_exists(conn, 'duty_events', 'ix_duty_events_event_type'):
        op.create_index('ix_duty_events_event_type', 'duty_events', ['event_type'])
    if _table_exists(conn, 'tracking_sessions') and not _index_exists(conn, 'tracking_sessions', 'ix_tracking_sessions_user_id'):
        op.create_index('ix_tracking_sessions_user_id', 'tracking_sessions', ['user_id'])
    if _table_exists(conn, 'tracking_sessions') and not _index_exists(conn, 'tracking_sessions', 'ix_tracking_sessions_shift_id'):
        op.create_index('ix_tracking_sessions_shift_id', 'tracking_sessions', ['shift_id'])
    if _table_exists(conn, 'tracking_sessions') and not _index_exists(conn, 'tracking_sessions', 'ix_tracking_sessions_started_at'):
        op.create_index('ix_tracking_sessions_started_at', 'tracking_sessions', ['started_at'])
    if _table_exists(conn, 'tracking_sessions') and not _index_exists(conn, 'tracking_sessions', 'ix_tracking_sessions_ended_at'):
        op.create_index('ix_tracking_sessions_ended_at', 'tracking_sessions', ['ended_at'])
    if _table_exists(conn, 'tracking_points') and not _index_exists(conn, 'tracking_points', 'ix_tracking_points_session_id'):
        op.create_index('ix_tracking_points_session_id', 'tracking_points', ['session_id'])
    if _table_exists(conn, 'tracking_points') and not _index_exists(conn, 'tracking_points', 'ix_tracking_points_user_id'):
        op.create_index('ix_tracking_points_user_id', 'tracking_points', ['user_id'])
    if _table_exists(conn, 'tracking_points') and not _index_exists(conn, 'tracking_points', 'ix_tracking_points_ts'):
        op.create_index('ix_tracking_points_ts', 'tracking_points', ['ts'])
    if _table_exists(conn, 'tracking_stops') and not _index_exists(conn, 'tracking_stops', 'ix_tracking_stops_session_id'):
        op.create_index('ix_tracking_stops_session_id', 'tracking_stops', ['session_id'])
    if _table_exists(conn, 'tracking_stops') and not _index_exists(conn, 'tracking_stops', 'ix_tracking_stops_start_ts'):
        op.create_index('ix_tracking_stops_start_ts', 'tracking_stops', ['start_ts'])
    if _table_exists(conn, 'tracking_stops') and not _index_exists(conn, 'tracking_stops', 'ix_tracking_stops_end_ts'):
        op.create_index('ix_tracking_stops_end_ts', 'tracking_stops', ['end_ts'])
    if _table_exists(conn, 'break_requests') and not _index_exists(conn, 'break_requests', 'ix_break_requests_user_id'):
        op.create_index('ix_break_requests_user_id', 'break_requests', ['user_id'])
    if _table_exists(conn, 'break_requests') and not _index_exists(conn, 'break_requests', 'ix_break_requests_shift_id'):
        op.create_index('ix_break_requests_shift_id', 'break_requests', ['shift_id'])
    if _table_exists(conn, 'break_requests') and not _index_exists(conn, 'break_requests', 'ix_break_requests_requested_at'):
        op.create_index('ix_break_requests_requested_at', 'break_requests', ['requested_at'])
    if _table_exists(conn, 'sos_alerts') and not _index_exists(conn, 'sos_alerts', 'ix_sos_alerts_user_id'):
        op.create_index('ix_sos_alerts_user_id', 'sos_alerts', ['user_id'])
    if _table_exists(conn, 'sos_alerts') and not _index_exists(conn, 'sos_alerts', 'ix_sos_alerts_shift_id'):
        op.create_index('ix_sos_alerts_shift_id', 'sos_alerts', ['shift_id'])
    if _table_exists(conn, 'sos_alerts') and not _index_exists(conn, 'sos_alerts', 'ix_sos_alerts_session_id'):
        op.create_index('ix_sos_alerts_session_id', 'sos_alerts', ['session_id'])
    if _table_exists(conn, 'sos_alerts') and not _index_exists(conn, 'sos_alerts', 'ix_sos_alerts_created_at'):
        op.create_index('ix_sos_alerts_created_at', 'sos_alerts', ['created_at'])
    if _table_exists(conn, 'duty_notifications') and not _index_exists(conn, 'duty_notifications', 'ix_duty_notifications_user_id'):
        op.create_index('ix_duty_notifications_user_id', 'duty_notifications', ['user_id'])
    if _table_exists(conn, 'duty_notifications') and not _index_exists(conn, 'duty_notifications', 'ix_duty_notifications_created_at'):
        op.create_index('ix_duty_notifications_created_at', 'duty_notifications', ['created_at'])
    if _table_exists(conn, 'duty_notifications') and not _index_exists(conn, 'duty_notifications', 'ix_duty_notifications_kind'):
        op.create_index('ix_duty_notifications_kind', 'duty_notifications', ['kind'])
    if _table_exists(conn, 'duty_notifications') and not _index_exists(conn, 'duty_notifications', 'ix_duty_notifications_acked'):
        op.create_index('ix_duty_notifications_acked', 'duty_notifications', ['acked'])
    if _table_exists(conn, 'tracker_pair_codes') and not _index_exists(conn, 'tracker_pair_codes', 'ix_tracker_pair_codes_created_at'):
        op.create_index('ix_tracker_pair_codes_created_at', 'tracker_pair_codes', ['created_at'])
    if _table_exists(conn, 'tracker_pair_codes') and not _index_exists(conn, 'tracker_pair_codes', 'ix_tracker_pair_codes_expires_at'):
        op.create_index('ix_tracker_pair_codes_expires_at', 'tracker_pair_codes', ['expires_at'])
    if _table_exists(conn, 'tracker_pair_codes') and not _index_exists(conn, 'tracker_pair_codes', 'ix_tracker_pair_codes_used_at'):
        op.create_index('ix_tracker_pair_codes_used_at', 'tracker_pair_codes', ['used_at'])
    if _table_exists(conn, 'tracker_devices') and not _index_exists(conn, 'tracker_devices', 'ix_tracker_devices_created_at'):
        op.create_index('ix_tracker_devices_created_at', 'tracker_devices', ['created_at'])
    if _table_exists(conn, 'tracker_devices') and not _index_exists(conn, 'tracker_devices', 'ix_tracker_devices_last_seen_at'):
        op.create_index('ix_tracker_devices_last_seen_at', 'tracker_devices', ['last_seen_at'])
    if _table_exists(conn, 'tracker_devices') and not _index_exists(conn, 'tracker_devices', 'ix_tracker_devices_is_revoked'):
        op.create_index('ix_tracker_devices_is_revoked', 'tracker_devices', ['is_revoked'])
    if _table_exists(conn, 'tracker_devices') and not _index_exists(conn, 'tracker_devices', 'ix_tracker_devices_user_id'):
        op.create_index('ix_tracker_devices_user_id', 'tracker_devices', ['user_id'])
    if _table_exists(conn, 'tracker_device_health') and not _index_exists(conn, 'tracker_device_health', 'ix_tracker_device_health_user_id'):
        op.create_index('ix_tracker_device_health_user_id', 'tracker_device_health', ['user_id'])
    if _table_exists(conn, 'tracker_device_health') and not _index_exists(conn, 'tracker_device_health', 'ix_tracker_device_health_updated_at'):
        op.create_index('ix_tracker_device_health_updated_at', 'tracker_device_health', ['updated_at'])
    if _table_exists(conn, 'tracker_device_health_log') and not _index_exists(conn, 'tracker_device_health_log', 'ix_tracker_device_health_log_user_id'):
        op.create_index('ix_tracker_device_health_log_user_id', 'tracker_device_health_log', ['user_id'])
    if _table_exists(conn, 'tracker_device_health_log') and not _index_exists(conn, 'tracker_device_health_log', 'ix_tracker_device_health_log_ts'):
        op.create_index('ix_tracker_device_health_log_ts', 'tracker_device_health_log', ['ts'])
    if _table_exists(conn, 'tracker_alerts') and not _index_exists(conn, 'tracker_alerts', 'ix_tracker_alerts_user_id'):
        op.create_index('ix_tracker_alerts_user_id', 'tracker_alerts', ['user_id'])
    if _table_exists(conn, 'tracker_alerts') and not _index_exists(conn, 'tracker_alerts', 'ix_tracker_alerts_created_at'):
        op.create_index('ix_tracker_alerts_created_at', 'tracker_alerts', ['created_at'])
    if _table_exists(conn, 'tracker_alerts') and not _index_exists(conn, 'tracker_alerts', 'ix_tracker_alerts_updated_at'):
        op.create_index('ix_tracker_alerts_updated_at', 'tracker_alerts', ['updated_at'])
    if _table_exists(conn, 'tracker_alerts') and not _index_exists(conn, 'tracker_alerts', 'ix_tracker_alerts_is_active'):
        op.create_index('ix_tracker_alerts_is_active', 'tracker_alerts', ['is_active'])
    if _table_exists(conn, 'tracker_admin_audit') and not _index_exists(conn, 'tracker_admin_audit', 'ix_tracker_admin_audit_ts'):
        op.create_index('ix_tracker_admin_audit_ts', 'tracker_admin_audit', ['ts'])


def downgrade():
    conn = op.get_bind()
    # drop indexes first
    for table_name, index_name in [
        ('duty_shifts', 'ix_duty_shifts_started_at'),
        ('duty_shifts', 'ix_duty_shifts_ended_at'),
        ('duty_events', 'ix_duty_events_user_id'),
        ('duty_events', 'ix_duty_events_shift_id'),
        ('duty_events', 'ix_duty_events_ts'),
        ('duty_events', 'ix_duty_events_event_type'),
        ('tracking_sessions', 'ix_tracking_sessions_user_id'),
        ('tracking_sessions', 'ix_tracking_sessions_shift_id'),
        ('tracking_sessions', 'ix_tracking_sessions_started_at'),
        ('tracking_sessions', 'ix_tracking_sessions_ended_at'),
        ('tracking_points', 'ix_tracking_points_session_id'),
        ('tracking_points', 'ix_tracking_points_user_id'),
        ('tracking_points', 'ix_tracking_points_ts'),
        ('tracking_stops', 'ix_tracking_stops_session_id'),
        ('tracking_stops', 'ix_tracking_stops_start_ts'),
        ('tracking_stops', 'ix_tracking_stops_end_ts'),
        ('break_requests', 'ix_break_requests_user_id'),
        ('break_requests', 'ix_break_requests_shift_id'),
        ('break_requests', 'ix_break_requests_requested_at'),
        ('sos_alerts', 'ix_sos_alerts_user_id'),
        ('sos_alerts', 'ix_sos_alerts_shift_id'),
        ('sos_alerts', 'ix_sos_alerts_session_id'),
        ('sos_alerts', 'ix_sos_alerts_created_at'),
        ('duty_notifications', 'ix_duty_notifications_user_id'),
        ('duty_notifications', 'ix_duty_notifications_created_at'),
        ('duty_notifications', 'ix_duty_notifications_kind'),
        ('duty_notifications', 'ix_duty_notifications_acked'),
        ('tracker_pair_codes', 'ix_tracker_pair_codes_created_at'),
        ('tracker_pair_codes', 'ix_tracker_pair_codes_expires_at'),
        ('tracker_pair_codes', 'ix_tracker_pair_codes_used_at'),
        ('tracker_devices', 'ix_tracker_devices_created_at'),
        ('tracker_devices', 'ix_tracker_devices_last_seen_at'),
        ('tracker_devices', 'ix_tracker_devices_is_revoked'),
        ('tracker_devices', 'ix_tracker_devices_user_id'),
        ('tracker_device_health', 'ix_tracker_device_health_user_id'),
        ('tracker_device_health', 'ix_tracker_device_health_updated_at'),
        ('tracker_device_health_log', 'ix_tracker_device_health_log_user_id'),
        ('tracker_device_health_log', 'ix_tracker_device_health_log_ts'),
        ('tracker_alerts', 'ix_tracker_alerts_user_id'),
        ('tracker_alerts', 'ix_tracker_alerts_created_at'),
        ('tracker_alerts', 'ix_tracker_alerts_updated_at'),
        ('tracker_alerts', 'ix_tracker_alerts_is_active'),
        ('tracker_admin_audit', 'ix_tracker_admin_audit_ts'),
    ]:
        if _table_exists(conn, table_name) and _index_exists(conn, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    # drop tables in reverse dependency order
    for table_name in [
        'tracker_admin_audit',
        'tracker_alerts',
        'tracker_device_health_log',
        'tracker_device_health',
        'tracker_devices',
        'tracker_pair_codes',
        'duty_notifications',
        'sos_alerts',
        'break_requests',
        'tracking_stops',
        'tracking_points',
        'tracking_sessions',
        'duty_events',
        'duty_shifts',
        'chat_messages',
        'chat_dialogs',
        'pending_history',
        'pending_markers',
        'addresses',
        'admin_users',
        'zone',
    ]:
        if _table_exists(conn, table_name):
            op.drop_table(table_name)
