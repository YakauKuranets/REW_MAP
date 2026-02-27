from __future__ import annotations


def _make_app(**overrides):
    from app import create_app
    from app.config import TestingConfig

    class C(TestingConfig):
        pass

    for k, v in overrides.items():
        setattr(C, k, v)

    return create_app(C)


def test_security_headers_present_on_responses():
    app = _make_app(ENABLE_METRICS=False)
    with app.test_client() as client:
        r = client.get("/")
        # страница может редиректить на /login, но headers должны быть.
        assert r.status_code in (200, 302)
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("Referrer-Policy") == "same-origin"


def test_metrics_remote_denied_without_key():
    app = _make_app(ENABLE_METRICS=True, METRICS_ALLOW_PUBLIC=False, METRICS_API_KEY="")
    with app.test_client() as client:
        r = client.get("/metrics", environ_base={"REMOTE_ADDR": "1.2.3.4"})
        assert r.status_code == 403


def test_metrics_remote_allowed_with_key():
    app = _make_app(ENABLE_METRICS=True, METRICS_ALLOW_PUBLIC=False, METRICS_API_KEY="m")
    with app.test_client() as client:
        r = client.get(
            "/metrics",
            environ_base={"REMOTE_ADDR": "1.2.3.4"},
            headers={"X-API-KEY": "m"},
        )
        assert r.status_code == 200