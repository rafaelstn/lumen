"""Teste de fumaça da Fase 1 — a aplicação sobe e o health check responde."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "1.0.0"}


def test_modulo01_status_ok():
    resp = client.get("/api/modulo01/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
