import os
from datetime import datetime

import shodan
from celery import shared_task

from app.extensions import db
SHODAN_API_KEY = os.environ.get('SHODAN_API_KEY', 'your_key_here')


def _global_camera_model():
    """Lazy import to avoid heavy video package side-effects during worker/test import."""
    from app.video.models import GlobalCamera

    return GlobalCamera


def _build_shodan_client(api_key: str, *, tor_session=None):
    """Create Shodan API client with optional requests session (Tor)."""
    if tor_session is None:
        return shodan.Shodan(api_key)
    try:
        return shodan.Shodan(api_key, requests_session=tor_session)
    except TypeError:
        # Compatibility: some shodan versions may not accept requests_session.
        return shodan.Shodan(api_key)


@shared_task
def scan_shodan_for_cameras(query='product:"Hikvision" OR product:"Dahua"', limit=100, use_tor=False):
    """
    Периодическая задача для сбора информации о камерах через Shodan.
    Результаты сохраняются в БД для последующего анализа.

    :param use_tor: если True, запросы к Shodan выполняются через Tor SOCKS5 прокси.
    """
    if not SHODAN_API_KEY or SHODAN_API_KEY == 'your_key_here':
        return 'Ошибка Shodan: SHODAN_API_KEY не задан'

    tor_client = None
    try:
        if use_tor:
            from app.network.tor_client import TorProxyClient

            tor_client = TorProxyClient()
            current_ip = tor_client.get_current_ip()
            if current_ip:
                print(f"[shodan] scanning with Tor IP: {current_ip}")

        api = _build_shodan_client(
            SHODAN_API_KEY,
            tor_session=(tor_client.session if tor_client is not None else None),
        )

        results = api.search(query, limit=limit)
        matches = results.get('matches', [])
        for match in matches:
            ip_value = match.get('ip_str')
            if not ip_value:
                continue

            GlobalCamera = _global_camera_model()
            existing = GlobalCamera.query.filter_by(ip=ip_value).first()
            data = {
                'ip': ip_value,
                'port': match.get('port', 80),
                'vendor': match.get('product'),
                'model': match.get('info'),
                'country': (match.get('location') or {}).get('country_name'),
                'city': (match.get('location') or {}).get('city'),
                'org': match.get('org'),
                'hostnames': match.get('hostnames', []),
                'vulnerabilities': match.get('vulns', []),
            }

            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
                existing.last_seen = datetime.utcnow()
            else:
                new_cam = GlobalCamera(**data, first_seen=datetime.utcnow())
                db.session.add(new_cam)

        db.session.commit()

        if tor_client is not None:
            tor_client.renew_identity()

        return f"Найдено {results.get('total', 0)} устройств, сохранено {len(matches)}"
    except Exception as e:
        db.session.rollback()
        return f"Ошибка Shodan: {e}"
    finally:
        if tor_client is not None:
            tor_client.close()
