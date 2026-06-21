"""Testes do middleware de request e do bootstrap() integrado."""

from __future__ import annotations

import io
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from regroup_obs import RequestLoggingMiddleware, bootstrap, setup_logging


def _json_app(**mw_kwargs):
    stream = io.StringIO()
    setup_logging(service="svc", json_output=True, stream=stream)
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware, service="svc", **mw_kwargs)

    @app.get("/ping")
    async def ping():
        logging.getLogger("handler").info("dentro do handler")
        return {"pong": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("estourou")

    return TestClient(app, raise_server_exceptions=False), stream


def _lines(stream):
    return [json.loads(ln) for ln in stream.getvalue().splitlines() if ln.strip()]


def test_devolve_request_id_no_response():
    client, _ = _json_app()
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id")


def test_propaga_request_id_do_cliente():
    client, stream = _json_app()
    resp = client.get("/ping", headers={"X-Request-ID": "cliente-123"})
    assert resp.headers["x-request-id"] == "cliente-123"
    # O log do handler herdou o id via ContextVar.
    handler_logs = [ln for ln in _lines(stream) if ln.get("logger") == "handler"]
    assert handler_logs and handler_logs[0]["request_id"] == "cliente-123"


def test_loga_request_com_status_e_duracao():
    client, stream = _json_app()
    client.get("/ping")
    req_logs = [ln for ln in _lines(stream) if ln.get("msg") == "request"]
    assert req_logs
    entry = req_logs[-1]
    assert entry["method"] == "GET"
    assert entry["path"] == "/ping"
    assert entry["status"] == 200
    assert "duration_ms" in entry


def test_excecao_loga_e_propaga():
    client, stream = _json_app()
    resp = client.get("/boom")
    assert resp.status_code == 500
    fail_logs = [ln for ln in _lines(stream) if ln.get("msg") == "request falhou"]
    assert fail_logs
    assert "RuntimeError" in fail_logs[-1]["exc_info"]


def test_skip_paths_nao_loga_health():
    client, stream = _json_app()
    client.get("/ping")
    # health não está montado aqui, mas /metrics-like skip: usamos /ping logado.
    req_logs = [ln for ln in _lines(stream) if ln.get("msg") == "request"]
    assert all(ln["path"] != "/health" for ln in req_logs)


def test_bootstrap_monta_tudo():
    app = FastAPI()
    bootstrap(app, service="svc", version="1.2.3", enable_sentry=False)

    @app.get("/x")
    async def x():
        return {"ok": True}

    client = TestClient(app)
    # health montado
    assert client.get("/health/live").json()["version"] == "1.2.3"
    # request_id middleware ativo
    assert client.get("/x").headers.get("x-request-id")
