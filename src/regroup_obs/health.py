"""Health check transativo para FastAPI.

Resolve o anti-padrão recorrente do portfólio: ``/health`` que retorna
``{"status": "ok"}`` incondicionalmente, sem tocar em DB/Redis/Supabase — um
load balancer feliz na frente de um serviço morto.

Separa liveness de readiness (convenção k8s, útil mesmo em VPS/systemd):

* ``GET /health/live``  — o processo está de pé? Sempre 200. Para auto-restart.
* ``GET /health/ready`` — as dependências respondem? 200 ou 503. Para LB/deploy.
* ``GET /health``       — alias de readiness (a maioria dos projetos só bate aqui).

Uso::

    from regroup_obs import build_health_router, Check

    async def _db() -> None:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    app.include_router(build_health_router(
        service="my-service",
        version="1.20.32",
        checks=[
            Check("postgres", _db),
            Check("redis", lambda: redis.ping(), critical=False),
        ],
    ))
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# Uma checagem é qualquer callable que: retorna (qualquer coisa) em sucesso,
# ou LEVANTA em falha. Pode ser sync ou async.
CheckFn = Callable[[], Any | Awaitable[Any]]


@dataclass
class Check:
    """Uma dependência a verificar.

    Args:
        name: identificador na resposta (ex.: "postgres", "supabase").
        fn: callable sync ou async; levanta para sinalizar falha.
        critical: se True (default), falha torna o serviço NOT ready (503).
            Use False para dependências degradáveis (ex.: cache opcional).
    """

    name: str
    fn: CheckFn
    critical: bool = True


async def _run_check(check: Check, timeout: float) -> dict[str, Any]:
    """Executa uma checagem isolando exceção e medindo latência."""
    started = time.perf_counter()
    try:
        result = check.fn()
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=timeout)
        else:
            # Offload de função síncrona (ex.: psycopg2) para não travar o loop.
            await asyncio.wait_for(asyncio.to_thread(lambda: result), timeout=timeout)
        ok, error = True, None
    except Exception as exc:  # noqa: BLE001 - qualquer falha = check vermelho
        ok, error = False, f"{type(exc).__name__}: {exc}"

    entry: dict[str, Any] = {
        "ok": ok,
        "critical": check.critical,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    if error is not None:
        entry["error"] = error
    return entry


def build_health_router(
    service: str,
    *,
    version: str = "unknown",
    checks: list[Check] | None = None,
    check_timeout: float = 5.0,
    prefix: str = "",
):
    """Constrói um APIRouter (FastAPI) com /health, /health/live e /health/ready.

    Args:
        service: nome do serviço, ecoado na resposta.
        version: versão/build do serviço (ex.: tag SemVer ou git sha).
        checks: dependências de readiness. Vazio → readiness sempre 200.
        check_timeout: timeout por checagem, em segundos.
        prefix: prefixo de rota opcional (ex.: "/api").

    Returns:
        fastapi.APIRouter pronto para app.include_router(...).
    """
    try:
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "build_health_router exige FastAPI. "
            "Instale com: pip install 'regroup-observability[fastapi]'"
        ) from exc

    checks = checks or []
    router = APIRouter(prefix=prefix, tags=["health"])

    @router.get("/health/live")
    async def live() -> dict[str, Any]:
        # Liveness não toca em dependências: responde se o processo está vivo.
        return {"status": "alive", "service": service, "version": version}

    @router.get("/health/ready")
    async def ready() -> Any:
        results = await asyncio.gather(*(_run_check(c, check_timeout) for c in checks))
        report = {c.name: r for c, r in zip(checks, results)}

        # Não-pronto somente se uma checagem CRÍTICA falhar. Não-críticas que
        # falham marcam o serviço como "degraded" mas ainda servível (200).
        failed_critical = [n for n, r in report.items() if not r["ok"] and r["critical"]]
        any_failure = any(not r["ok"] for r in report.values())

        if failed_critical:
            status, code = "unavailable", 503
        elif any_failure:
            status, code = "degraded", 200
        else:
            status, code = "ready", 200

        return JSONResponse(
            status_code=code,
            content={
                "status": status,
                "service": service,
                "version": version,
                "checks": report,
            },
        )

    @router.get("/health")
    async def health() -> Any:
        # Alias de readiness para compatibilidade com os health checks existentes.
        return await ready()

    return router
