# regroup-observability

Regras globais de engenharia da Re.Group valem aqui (`~/.claude/CLAUDE.md` e `~/AGENTS.md`). Este arquivo traz só o que é específico do projeto.

## Comandos
```bash
pytest
ruff check .
```
Se um comando falhar por ambiente, diga que não conseguiu validar. Não declare "pronto" sem rodar as verificações acima.

## Limites
- Trabalhe numa branch por mudança; não commite direto em `main` sem confirmação.
- Não leia, edite nem imprima `.env` ou credenciais; use `.env.example` como referência.
- Nenhum dado de cliente (CPF, processo, documento) em código, log, teste ou mensagem de commit.
- Revisão dupla: quem implementou não se autoaprova. O revisor trabalha em modo somente leitura e separa defeito confirmado de hipótese.

## Objetivo e estrutura
Pacote pip de observabilidade compartilhada dos serviços FastAPI da Re.Group: logging JSON estruturado com correlação por `request_id`, Sentry com inicialização tolerante e uma terceira lacuna descrita no README. Estrutura: `src/`, `tests/`, `starter/`, `ci/`.

## Consumidores
Confirmado pelo dono do projeto: `simulador-renegociacao` e `diagnostico-empresas-familiares` / `credito-estruturado` usam este pacote. Mudança de interface pública (nomes de funções, formato do log JSON, campos de `request_id`) quebra esses serviços: ao mudar, avisar e verificar os três.

## Pendente de preencher pelo dono do projeto
- Política de versionamento e como os consumidores atualizam.
- Comando de teste (há `[tool.pytest.ini_options]`).
