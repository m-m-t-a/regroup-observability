"""Inicialização de Sentry tolerante a ausência.

Fecha o padrão recorrente do portfólio: "Sentry DSN no .env mas nunca
inicializado no código". Aqui a chamada é segura de fazer incondicionalmente
no startup — ela vira no-op se o SDK não estiver instalado ou o DSN não estiver
configurado, e retorna um booleano dizendo se ativou.

    from regroup_obs import init_sentry
    init_sentry(service="my-service")  # lê SENTRY_DSN / ENVIRONMENT do ambiente
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)


def init_sentry(
    service: str,
    *,
    dsn: str | None = None,
    environment: str | None = None,
    release: str | None = None,
    traces_sample_rate: float = 0.0,
    **extra: object,
) -> bool:
    """Inicializa o Sentry se possível. Retorna True se ativou, False se no-op.

    Args:
        service: nome do serviço, vira a tag ``service``.
        dsn: sobrescreve SENTRY_DSN do ambiente.
        environment: sobrescreve ENVIRONMENT (default "production").
        release: versão/commit; default lê GIT_SHA ou RELEASE do ambiente.
        traces_sample_rate: amostragem de performance (0.0 desliga tracing).
        **extra: repassado direto para sentry_sdk.init (ex.: profiles_sample_rate).

    Nunca levanta: qualquer falha é logada como warning e vira no-op, porque
    observabilidade quebrada jamais deve derrubar o serviço observado.
    """
    resolved_dsn = dsn or os.getenv("SENTRY_DSN")
    if not resolved_dsn:
        _log.info("Sentry desativado: SENTRY_DSN ausente", extra={"service": service})
        return False

    try:
        import sentry_sdk
    except ImportError:
        _log.warning(
            "Sentry desativado: pacote sentry-sdk não instalado "
            "(instale com regroup-observability[sentry])",
            extra={"service": service},
        )
        return False

    try:
        sentry_sdk.init(
            dsn=resolved_dsn,
            environment=environment or os.getenv("ENVIRONMENT", "production"),
            release=release or os.getenv("GIT_SHA") or os.getenv("RELEASE"),
            traces_sample_rate=traces_sample_rate,
            **extra,
        )
        sentry_sdk.set_tag("service", service)
    except Exception as exc:  # noqa: BLE001 - blindagem deliberada
        _log.warning("Falha ao inicializar Sentry: %s", exc, extra={"service": service})
        return False

    _log.info("Sentry ativo", extra={"service": service})
    return True
