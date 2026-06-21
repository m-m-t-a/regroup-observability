"""Middleware ASGI de logging de requisição — dependência zero.

Implementado como ASGI puro (não Starlette BaseHTTPMiddleware) para funcionar em
qualquer app ASGI sem somar dependências e sem o overhead/edge-cases de streaming
do BaseHTTPMiddleware.

Para cada requisição:
  * lê ``X-Request-ID`` do cliente ou gera um UUID4;
  * vincula o id ao ContextVar — todo log da requisição passa a correlacionar;
  * emite uma linha JSON ao final com método, rota, status e latência;
  * devolve ``X-Request-ID`` no response para rastreio ponta a ponta.

Uso::

    from regroup_obs import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware, service="my-service")
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable

from .logging import request_id_ctx

_log = logging.getLogger("regroup_obs.request")

_HEADER = b"x-request-id"


class RequestLoggingMiddleware:
    """Middleware ASGI que correlaciona e registra requisições HTTP."""

    def __init__(
        self,
        app: Callable,
        *,
        service: str = "app",
        logger: logging.Logger | None = None,
        skip_paths: tuple[str, ...] = ("/health", "/health/live", "/health/ready", "/metrics"),
    ) -> None:
        self.app = app
        self.service = service
        self.logger = logger or _log
        self.skip_paths = skip_paths

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(_HEADER)
        request_id = incoming.decode() if incoming else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)

        status_holder = {"code": 0}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                # Devolve o id ao cliente para correlação ponta a ponta.
                raw = list(message.get("headers") or [])
                raw.append((_HEADER, request_id.encode()))
                message = {**message, "headers": raw}
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Loga a falha não-tratada (com stack) e re-levanta — o tratamento de
            # erro do framework/Sentry continua responsável pela resposta.
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            self.logger.exception(
                "request falhou",
                extra={
                    "method": scope.get("method"),
                    "path": path,
                    "status": 500,
                    "duration_ms": elapsed,
                },
            )
            raise
        finally:
            request_id_ctx.reset(token)

        if path not in self.skip_paths:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            code = status_holder["code"]
            self.logger.log(
                logging.WARNING if code >= 500 else logging.INFO,
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": path,
                    "status": code,
                    "duration_ms": elapsed,
                },
            )
