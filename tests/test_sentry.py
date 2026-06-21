"""Testes do init_sentry: no-op seguro sem DSN / sem SDK, ativa com mock."""

from __future__ import annotations

import sys
import types

from regroup_obs import init_sentry


def test_noop_sem_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry(service="svc") is False


def test_noop_se_sdk_ausente(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://x@example.com/1")
    # Simula sentry_sdk não instalado.
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    assert init_sentry(service="svc") is False


def test_ativa_com_sdk_mockado(monkeypatch):
    calls = {}

    fake = types.ModuleType("sentry_sdk")
    fake.init = lambda **kw: calls.update(init=kw)
    fake.set_tag = lambda k, v: calls.setdefault("tags", {}).update({k: v})
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    monkeypatch.setenv("SENTRY_DSN", "https://x@example.com/1")

    assert init_sentry(service="svc", release="1.0.0") is True
    assert calls["init"]["dsn"] == "https://x@example.com/1"
    assert calls["init"]["release"] == "1.0.0"
    assert calls["tags"]["service"] == "svc"


def test_falha_no_init_nao_levanta(monkeypatch):
    def explode(**kw):
        raise RuntimeError("init quebrou")

    fake = types.ModuleType("sentry_sdk")
    fake.init = explode
    fake.set_tag = lambda *a: None
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    monkeypatch.setenv("SENTRY_DSN", "https://x@example.com/1")

    # Não deve propagar — observabilidade quebrada não derruba o serviço.
    assert init_sentry(service="svc") is False
