from __future__ import annotations

import types

from app.network.tor_client import TorProxyClient


def test_tor_client_sets_socks_proxy():
    client = TorProxyClient(tor_host="127.0.0.1", tor_port=19050)
    try:
        assert client.session.proxies["http"] == "socks5h://127.0.0.1:19050"
        assert client.session.proxies["https"] == "socks5h://127.0.0.1:19050"
    finally:
        client.close()


def test_renew_identity_uses_stem(monkeypatch):
    called = {"auth": 0, "signal": 0}

    class FakeController:
        @classmethod
        def from_port(cls, address, port):
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def authenticate(self, password=None):
            called["auth"] += 1

        def signal(self, _signal):
            called["signal"] += 1

    fake_stem = types.ModuleType("stem")
    fake_stem.Signal = types.SimpleNamespace(NEWNYM="NEWNYM")
    fake_stem_control = types.ModuleType("stem.control")
    fake_stem_control.Controller = FakeController

    import sys

    monkeypatch.setitem(sys.modules, "stem", fake_stem)
    monkeypatch.setitem(sys.modules, "stem.control", fake_stem_control)

    client = TorProxyClient()
    assert client.renew_identity(wait_sec=0)
    assert called == {"auth": 1, "signal": 1}
