"""Testes do logging JSON estruturado e correlação por request_id."""

from __future__ import annotations

import io
import json
import logging

from regroup_obs import setup_logging
from regroup_obs.logging import set_request_id, request_id_ctx


def _capture(json_output=True):
    stream = io.StringIO()
    setup_logging(service="svc-test", level="DEBUG", json_output=json_output, stream=stream)
    return stream


def _last_line(stream: io.StringIO) -> dict:
    lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
    return json.loads(lines[-1])


def test_emite_json_de_uma_linha():
    stream = _capture()
    logging.getLogger("x").info("ola mundo")
    record = _last_line(stream)
    assert record["msg"] == "ola mundo"
    assert record["service"] == "svc-test"
    assert record["level"] == "INFO"
    assert "ts" in record


def test_campos_extra_viram_chaves():
    stream = _capture()
    logging.getLogger("x").info("lead pontuado", extra={"lead_id": 42, "score": 91})
    record = _last_line(stream)
    assert record["lead_id"] == 42
    assert record["score"] == 91


def test_request_id_correlaciona_quando_setado():
    stream = _capture()
    token = set_request_id("req-abc")
    try:
        logging.getLogger("x").info("dentro da request")
    finally:
        request_id_ctx.reset(token)
    record = _last_line(stream)
    assert record["request_id"] == "req-abc"


def test_sem_request_id_nao_inclui_chave():
    stream = _capture()
    logging.getLogger("x").info("fora de request")
    assert "request_id" not in _last_line(stream)


def test_excecao_serializa_sem_quebrar():
    stream = _capture()
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("x").exception("falhou")
    record = _last_line(stream)
    assert "exc_info" in record
    assert "ValueError" in record["exc_info"]


def test_tipo_nao_serializavel_nao_derruba_log():
    stream = _capture()

    class Weird:
        def __repr__(self):
            return "<weird>"

    logging.getLogger("x").info("obj", extra={"thing": Weird()})
    record = _last_line(stream)
    assert record["thing"] == "<weird>"


def test_setup_idempotente_nao_duplica_handlers():
    stream = io.StringIO()
    setup_logging(service="a", json_output=True, stream=stream)
    setup_logging(service="b", json_output=True, stream=stream)
    logging.getLogger("x").info("uma vez")
    lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1  # não duplicou
    assert json.loads(lines[0])["service"] == "b"
