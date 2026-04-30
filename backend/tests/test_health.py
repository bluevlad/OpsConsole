"""GET /api/health 단위 테스트."""
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "opsconsole-backend"
    assert "checked_at" in body
