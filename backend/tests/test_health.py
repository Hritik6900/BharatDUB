from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_booleans_only():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert all(isinstance(v, bool) for v in body["configured"].values())
