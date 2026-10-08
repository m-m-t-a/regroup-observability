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

## Pendente de preencher pelo dono do projeto
- Versionamento e quem consome o pacote.
- Comando de teste (há `[tool.pytest.ini_options]`).
