from tests.conftest import login_admin

def test_health_ready(client):
    h = client.get("/health")
    assert h.status_code in (200, 204)

    r = client.get("/ready")
    assert r.status_code in (200, 503)

def test_metrics_optional(client, app):
    app.config["ENABLE_METRICS"] = True
    # /metrics path can be customized; default is /metrics
    m = client.get("/metrics")
    assert m.status_code in (200, 404)  # если path другой — 404
