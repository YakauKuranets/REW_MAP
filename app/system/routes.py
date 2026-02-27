from __future__ import annotations

import socket
from typing import List, Set

from compat_flask import jsonify, request, current_app

from . import bp
from ..helpers import require_admin


def _is_good_ipv4(ip: str) -> bool:
    ip = (ip or "").strip()
    if not ip:
        return False
    if ip.startswith("127."):
        return False
    if ip.startswith("0."):
        return False
    if ip.startswith("169.254."):
        return False
    try:
        socket.inet_aton(ip)
    except Exception:
        return False
    return True


def _unique_ipv4_addrs() -> List[str]:
    """Best-effort list of local IPv4 addresses."""
    ips: Set[str] = set()

    # 1) Hostname resolution
    try:
        host = socket.gethostname()
        for _family, _socktype, _proto, _canon, sockaddr in socket.getaddrinfo(host, None):
            try:
                ip = sockaddr[0]
                if _is_good_ipv4(ip):
                    ips.add(ip)
            except Exception:
                pass
    except Exception:
        pass

    # 2) Default route IP (UDP trick, no traffic is sent)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if _is_good_ipv4(ip):
                ips.add(ip)
        finally:
            try:
                s.close()
            except Exception:
                pass
    except Exception:
        pass

    # Stable ordering
    return sorted(ips)


def _guess_port() -> int:
    # Prefer current request host:port
    try:
        host = (request.host or "").strip()
        if ":" in host:
            port_s = host.rsplit(":", 1)[-1]
            return int(port_s)
    except Exception:
        pass
    return 5000


def _recommended_base_urls(ips: List[str], port: int) -> List[str]:
    return [f"http://{ip}:{port}" for ip in ips]


@bp.get("/lan-info")
def lan_info():
    """Return LAN/VPN IPv4 addresses and recommended base URLs.

    Auth: web admin session.
    """
    require_admin(min_role="editor")

    port = _guess_port()
    ips = _unique_ipv4_addrs()

    preferred = (current_app.config.get("BOOTSTRAP_PREFERRED_BASE_URL") or "").strip().rstrip("/")
    current_origin = (request.url_root or "").rstrip("/")

    # If the request comes through trycloudflare, ensure https in UI hints.
    host = (request.host or "").lower().strip()
    if host.endswith("trycloudflare.com") and current_origin.startswith("http://"):
        current_origin = "https://" + current_origin[len("http://"):]

    recommended: List[str] = []
    if preferred:
        recommended.append(preferred)
    if current_origin and current_origin not in recommended:
        recommended.append(current_origin)

    for u in _recommended_base_urls(ips, port):
        if u not in recommended:
            recommended.append(u)

    return jsonify(
        {
            "ips": ips,
            "port": port,
            "preferred_base_url": preferred,
            "current_origin": current_origin,
            "recommended_base_urls": recommended,
            "note": "Computed on server; UI can use preferred_base_url to avoid LAN IP guessing.",
        }
    ), 200
