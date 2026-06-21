# regroup-observability

Observabilidade compartilhada dos serviços **FastAPI** da Re.Group. Um único
pacote, instalável via pip, que padroniza três lacunas sistêmicas comuns
em serviços FastAPI:

1. **Logging JSON estruturado** com correlação por `request_id` — substitui
   `print()`/`console.log` soltos.
2. **Sentry** com inicialização tolerante — fecha o "DSN no `.env` mas nunca
   inicializado no código".
3. **`/health` transativo** — readiness que de fato toca em DB/Redis/Supabase,
   em vez de `{"status": "ok"}` incondicional.

> **Escopo v1:** serviços **Python/FastAPI**. Node/Next ficam para a v2.
> Para serviços que não podem somar a dependência, use o starter copiável e
> zero-dependência em [`starter/`](starter/).

## Instalação

Em cada projeto, no `requirements.txt`:

```
regroup-observability[fastapi,sentry] @ git+https://github.com/m-m-t-a/regroup-observability@v0.1.0
```

Extras: `fastapi` (health router), `sentry` (sentry-sdk), `redis` (helper de ping).
O núcleo de logging não tem dependências e funciona em workers/CLIs sem framework.

## Uso — caminho feliz (uma linha)

```python
from fastapi import FastAPI
from regroup_obs import bootstrap, Check

app = FastAPI()

async def _db():
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")

bootstrap(
    app,
    service="my-service",
    version="1.20.32",                 # tag SemVer ou git sha
    checks=[Check("postgres", _db)],   # readiness real
)
```

Isso conecta: `setup_logging` + `init_sentry` (se `SENTRY_DSN` existir) +
`RequestLoggingMiddleware` + rotas `/health`, `/health/live`, `/health/ready`.

## Uso — peças soltas

```python
from regroup_obs import setup_logging, init_sentry, build_health_router, Check

setup_logging(service="my-service", json_output=True)   # dev: json_output=False
init_sentry(service="my-service")

app.include_router(build_health_router(
    service="my-service",
    version="0.3.1",
    checks=[
        Check("supabase", lambda: sb.table("leads").select("id").limit(1).execute()),
        Check("anthropic", ping_anthropic, critical=False),  # degradável
    ],
))
```

### Contrato de readiness

| Situação | `/health/ready` | `status` |
|----------|:---------------:|----------|
| Todas as checagens passam | 200 | `ready` |
| Falha **não-crítica** (`critical=False`) | 200 | `degraded` |
| Falha **crítica** | 503 | `unavailable` |

Liveness (`/health/live`) nunca toca em dependências — é só "o processo está
vivo?", para auto-restart do systemd/k8s sem derrubar por dependência lenta.

## Logs

Cada log vira uma linha JSON; campos `extra={...}` viram chaves; o `request_id`
da requisição corrente é injetado automaticamente:

```json
{"ts":"2026-06-21T20:14:02+00:00","level":"INFO","service":"my-service","env":"production","logger":"app.scorer","msg":"lead pontuado","request_id":"a1b2c3","lead_id":42,"score":91}
```

## Desenvolvimento

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```

## CI compartilhado

`ci/reusable-python-ci.yml` é um *reusable workflow* com gate de testes
(ruff → mypy opcional → pytest). Cada projeto o chama com ~6 linhas — ver
[`ci/example-caller.yml`](ci/example-caller.yml).
