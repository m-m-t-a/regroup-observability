"""Logging JSON estruturado, zero-dependência.

Substitui o padrão recorrente do portfólio (`print()` / `console.log` solto)
por logs em uma linha JSON, parseáveis por journald/Loki/Datadog, com
correlação de requisições via ``request_id`` propagado por ContextVar.

Uso mínimo::

    from regroup_obs import setup_logging
    setup_logging(service="my-service")

    import logging
    logging.getLogger(__name__).info("lead pontuado", extra={"lead_id": 42, "score": 91})
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Correlação de requisição. O middleware ASGI seta isto por request; qualquer
# log emitido durante o tratamento herda o id automaticamente.
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "regroup_request_id", default=None
)

# Campos que o logging já coloca no LogRecord e que NÃO devem ser tratados como
# "extra" do usuário ao serializar.
_STANDARD_FIELDS = frozenset(
    vars(logging.makeLogRecord({})).keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Formata cada LogRecord como um objeto JSON de uma linha."""

    def __init__(self, service: str, environment: str = "production") -> None:
        super().__init__()
        self.service = service
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "env": self.environment,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        request_id = request_id_ctx.get()
        if request_id is not None:
            payload["request_id"] = request_id

        # Campos arbitrários passados via logging.*(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # default=str garante que tipos não-serializáveis (datetime, UUID, Decimal)
        # nunca derrubem o logging — perdemos fidelidade, não a linha.
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(
    service: str,
    *,
    level: str | int = "INFO",
    environment: str = "production",
    json_output: bool = True,
    stream: Any | None = None,
    silence: tuple[str, ...] = ("uvicorn.access",),
) -> logging.Logger:
    """Configura o root logger do processo de forma idempotente.

    Chame uma vez no startup. Rechamar substitui os handlers anteriores em vez
    de empilhar (evita logs duplicados em --reload).

    Args:
        service: nome do serviço (ex.: "my-service"). Vai em todo log.
        level: nível mínimo. Aceita "DEBUG"/"INFO"/... ou int.
        environment: "production" | "staging" | "development".
        json_output: False usa formato texto legível (útil em dev local).
        stream: destino (default stdout).
        silence: loggers a rebaixar para WARNING (ex.: uvicorn.access duplica
            o que nosso middleware já registra de forma estruturada).

    Returns:
        O root logger configurado.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Idempotência: remove handlers que nós mesmos instalamos antes.
    for handler in list(root.handlers):
        if getattr(handler, "_regroup_obs", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler._regroup_obs = True  # type: ignore[attr-defined]
    if json_output:
        handler.setFormatter(JsonFormatter(service=service, environment=environment))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s :: %(message)s")
        )
    root.addHandler(handler)

    for name in silence:
        logging.getLogger(name).setLevel(logging.WARNING)

    return root


def set_request_id(request_id: str | None) -> contextvars.Token:
    """Vincula um request_id ao contexto atual. Retorna token para reset()."""
    return request_id_ctx.set(request_id)


def get_request_id() -> str | None:
    """Lê o request_id do contexto atual (None fora de uma requisição)."""
    return request_id_ctx.get()
