"""regroup_obs — observabilidade compartilhada Re.Group.

Logging JSON estruturado + Sentry + /health transativo, padronizados para os
serviços FastAPI do portfólio. Importe as peças soltas ou use ``bootstrap()``
para conectar todas de uma vez.

Setup mínimo num serviço FastAPI::

    from fastapi import FastAPI
    from regroup_obs import bootstrap, Check

    app = FastAPI()

    async def _db():
        async with pool.acquire() as c:
            await c.fetchval("SELECT 1")

    bootstrap(app, service="my-service", version="1.20.32", checks=[Check("postgres", _db)])
"""

from __future__ import annotations

from typing import Any

from .health import Check, build_health_router
from .logging import (
    JsonFormatter,
    get_request_id,
    set_request_id,
    setup_logging,
)
from .middleware import RequestLoggingMiddleware
from .sentry import init_sentry

__version__ = "0.1.0"

__all__ = [
    "bootstrap",
    "setup_logging",
    "init_sentry",
    "build_health_router",
    "Check",
    "RequestLoggingMiddleware",
    "JsonFormatter",
    "get_request_id",
    "set_request_id",
    "__version__",
]


def bootstrap(
    app: Any,
    *,
    service: str,
    version: str = "unknown",
    checks: list[Check] | None = None,
    level: str | int = "INFO",
    environment: str = "production",
    json_logs: bool = True,
    enable_sentry: bool = True,
    enable_request_log: bool = True,
) -> None:
    """Conecta logging + Sentry + health + middleware num app FastAPI.

    Idempotente o suficiente para chamar uma vez no startup. Cada peça pode ser
    desligada via flag para casos que precisam de controle fino.

    Args:
        app: instância FastAPI.
        service: nome do serviço, propagado a logs/sentry/health.
        version: versão/build (tag SemVer ou git sha).
        checks: dependências de readiness (ver Check).
        level: nível mínimo de log.
        environment: "production" | "staging" | "development".
        json_logs: False usa formato texto legível (dev local).
        enable_sentry: inicializa Sentry se SENTRY_DSN existir.
        enable_request_log: adiciona o middleware de logging de requisição.
    """
    setup_logging(
        service=service,
        level=level,
        environment=environment,
        json_output=json_logs,
    )

    if enable_sentry:
        init_sentry(service=service, environment=environment, release=version)

    if enable_request_log:
        app.add_middleware(RequestLoggingMiddleware, service=service)

    app.include_router(build_health_router(service=service, version=version, checks=checks))
