"""Testes do /health transativo: liveness sempre ok, readiness reflete dependências."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from regroup_obs import Check, build_health_router


def _app(checks):
    app = FastAPI()
    app.include_router(build_health_router(service="svc", version="9.9.9", checks=checks))
    return TestClient(app)


def test_live_sempre_200():
    client = _app([])
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"
    assert resp.json()["version"] == "9.9.9"


def test_ready_sem_checks_e_200():
    client = _app([])
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_ready_200_quando_todas_passam():
    async def ok_async():
        return True

    client = _app([Check("db", lambda: True), Check("cache", ok_async)])
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["db"]["ok"] is True
    assert "latency_ms" in body["checks"]["db"]


def test_ready_503_quando_check_critico_falha():
    def broken():
        raise ConnectionError("db down")

    client = _app([Check("postgres", broken)])
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["postgres"]["ok"] is False
    assert "ConnectionError" in body["checks"]["postgres"]["error"]


def test_check_nao_critico_falho_e_degraded_mas_200():
    def broken():
        raise TimeoutError("cache lenta")

    client = _app([Check("db", lambda: True), Check("cache", broken, critical=False)])
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


def test_health_e_alias_de_ready():
    def broken():
        raise RuntimeError("x")

    client = _app([Check("db", broken)])
    assert client.get("/health").status_code == 503


def test_timeout_de_check_vira_falha():
    import asyncio

    async def trava():
        await asyncio.sleep(10)

    app = FastAPI()
    app.include_router(
        build_health_router(service="svc", checks=[Check("lento", trava)], check_timeout=0.1)
    )
    client = TestClient(app)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert "TimeoutError" in resp.json()["checks"]["lento"]["error"]
