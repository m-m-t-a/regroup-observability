"""obs_dropin.py — observabilidade Re.Group em um único arquivo, zero-dependência.

FALLBACK copiável para serviços que NÃO podem adicionar a dependência
`regroup-observability` (ex.: ambientes air-gapped, scripts, ou enquanto o
pacote pip não está publicado). Cole este arquivo no projeto e importe dele.

A FONTE DA VERDADE é o pacote `regroup_obs`. Este drop-in é um subconjunto
mínimo (logging JSON + request_id + /health) mantido em paridade manual.
Prefira `pip install regroup-observability[fastapi]` sempre que possível.

    from obs_dropin import setup_logging, mount_health, Check
    setup_logging(service="meu-svc")
    mount_health(app, service="meu-svc", checks=[Check("db", ping)])
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("rid", default=None)
_STD = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime", "taskName"}


class _JsonFormatter(logging.Formatter):
    def __init__(self, service: str, env: str = "production"):
        super().__init__()
        self.service, self.env = service, env

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "env": self.env,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = _request_id.get()
        if rid:
            out["request_id"] = rid
        for k, v in record.__dict__.items():
            if k not in _STD and not k.startswith("_"):
                out[k] = v
        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def setup_logging(service: str, *, level="INFO", env="production", json_output=True, stream=None):
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        if getattr(h, "_dropin", False):
            root.removeHandler(h)
    h = logging.StreamHandler(stream or sys.stdout)
    h._dropin = True  # type: ignore[attr-defined]
    h.setFormatter(
        _JsonFormatter(service, env)
        if json_output
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s :: %(message)s")
    )
    root.addHandler(h)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return root


@dataclass
class Check:
    name: str
    fn: Callable[[], Any]
    critical: bool = True


async def _run(check: Check, timeout: float) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = check.fn()
        if inspect.isawaitable(r):
            await asyncio.wait_for(r, timeout)
        else:
            await asyncio.wait_for(asyncio.to_thread(lambda: r), timeout)
        ok, err = True, None
    except Exception as e:  # noqa: BLE001
        ok, err = False, f"{type(e).__name__}: {e}"
    entry = {"ok": ok, "critical": check.critical,
             "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    if err:
        entry["error"] = err
    return entry


def mount_health(app, *, service: str, version="unknown", checks=None, timeout=5.0):
    """Monta /health, /health/live, /health/ready num app FastAPI."""
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse

    checks = checks or []
    r = APIRouter(tags=["health"])

    @r.get("/health/live")
    async def live():
        return {"status": "alive", "service": service, "version": version}

    @r.get("/health/ready")
    async def ready():
        results = await asyncio.gather(*(_run(c, timeout) for c in checks))
        report = {c.name: res for c, res in zip(checks, results)}
        crit_fail = [n for n, x in report.items() if not x["ok"] and x["critical"]]
        any_fail = any(not x["ok"] for x in report.values())
        status, code = (
            ("unavailable", 503) if crit_fail else ("degraded", 200) if any_fail else ("ready", 200)
        )
        return JSONResponse(
            status_code=code,
            content={"status": status, "service": service,
                     "version": version, "checks": report},
        )

    @r.get("/health")
    async def health():
        return await ready()

    app.include_router(r)


def request_id_middleware_factory(service: str = "app"):
    """Retorna um middleware ASGI que correlaciona requisições por request_id."""

    def make(app):
        async def mw(scope, receive, send):
            if scope["type"] != "http":
                await app(scope, receive, send)
                return
            headers = dict(scope.get("headers") or [])
            raw = headers.get(b"x-request-id")
            rid = raw.decode() if raw else uuid.uuid4().hex
            tok = _request_id.set(rid)

            async def send_wrap(msg):
                if msg["type"] == "http.response.start":
                    hs = list(msg.get("headers") or [])
                    hs.append((b"x-request-id", rid.encode()))
                    msg = {**msg, "headers": hs}
                await send(msg)

            try:
                await app(scope, receive, send_wrap)
            finally:
                _request_id.reset(tok)

        return mw

    return make
