"""Endpoints for terminal connection checks (HIK/FTP)."""

from __future__ import annotations

import ftplib
from typing import Any, Dict

import requests
from compat_flask import jsonify, request
from requests.auth import HTTPDigestAuth

from . import bp


@bp.post('/test-connection')
def test_terminal_connection():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}

    ip = str(payload.get('ip') or '').strip()
    login = str(payload.get('login') or '').strip()
    password = str(payload.get('password') or '').strip()
    terminal_type = str(payload.get('type') or '').strip().upper()

    if not ip or not login or not password or not terminal_type:
        return jsonify({'status': 'error', 'message': 'ip, login, password, type are required'}), 400

    try:
        if terminal_type == 'HIK':
            url = f'http://{ip}/ISAPI/System/status'
            resp = requests.get(
                url,
                auth=HTTPDigestAuth(login, password),
                timeout=3,
            )
            if 200 <= resp.status_code < 300:
                return jsonify({'status': 'success'}), 200
            return jsonify({'status': 'error', 'message': f'HIK auth failed: HTTP {resp.status_code}'}), 200

        if terminal_type == 'FTP':
            ftp = ftplib.FTP()
            try:
                ftp.connect(host=ip, timeout=5)
                ftp.login(user=login, passwd=password)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()
            return jsonify({'status': 'success'}), 200

        return jsonify({'status': 'error', 'message': 'type must be HIK or FTP'}), 400
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 200
