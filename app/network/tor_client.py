# -*- coding: utf-8 -*-
"""Backward-compatible wrappers for proxy client utilities."""

from app.network.proxy_client import check_current_ip, get_proxy_session


class TorProxyClient:
    """Compatibility class kept for legacy imports."""

    def __init__(self, *_args, **_kwargs):
        self.session = get_proxy_session()

    def get(self, *args, **kwargs):
        return self.session.get(*args, **kwargs)


def get_tor_session():
    return get_proxy_session()


def check_tor_ip():
    return check_current_ip()
