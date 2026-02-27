from __future__ import annotations

import json
import threading

from compat_flask import Blueprint
from flask_sock import Sock

from app.extensions import redis_client
from app.realtime.tokens import verify_websocket_token
from app.security.aegis_soar import block_ip_sync

ws_bp = Blueprint('ws', __name__)
sock = Sock()


@sock.route('/ws/task')
def ws_task(ws):
    token = ws.receive(timeout=5)
    if not token:
        ip = (getattr(ws, "environ", {}) or {}).get("REMOTE_ADDR")
        if ip:
            block_ip_sync(ip, "WebSocket token missing")
        ws.close(reason='Token missing')
        return

    payload = verify_websocket_token(token)
    if not payload:
        ip = (getattr(ws, "environ", {}) or {}).get("REMOTE_ADDR")
        if ip:
            block_ip_sync(ip, "WebSocket invalid token brute-force")
        ws.close(reason='Invalid token')
        return

    task_id = payload.get('task_id')
    if not task_id:
        ws.close(reason='Invalid payload')
        return

    channel = payload.get('channel') or f'task:{task_id}'

    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)

    stop_flag = {'stop': False}

    def redis_listener():
        for message in pubsub.listen():
            if stop_flag['stop']:
                break
            if message.get('type') != 'message':
                continue
            data = message.get('data')
            try:
                if isinstance(data, (dict, list)):
                    ws.send(json.dumps(data, ensure_ascii=False))
                else:
                    ws.send(str(data))
            except Exception:
                break

    listener_thread = threading.Thread(target=redis_listener, daemon=True)
    listener_thread.start()

    try:
        while True:
            data = ws.receive(timeout=1)
            if data is None:
                break
    finally:
        stop_flag['stop'] = True
        try:
            pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            pubsub.close()
        except Exception:
            pass
