# Experimento 002 — Clean Code na prática (`lst env-check`)

Conteúdo desta pasta:

| Arquivo | O que é |
|---|---|
| `relato-clean-code-resumido.md` | **A entrega do exercício** (versão breve): problema, critérios, leitura crítica, revisão, antes/depois, verificações, comentários e reflexão |
| `relato-clean-code.md` | Versão detalhada da mesma entrega (apêndice: tabelas completas, quatro trechos antes/depois, evidências) |
| `tarefa-002-env-check.md` | Parte variável (contrato, exemplos N/L/E, critérios de Clean Code) — com a revisão 2 (esclarecimentos) ao final |
| (raiz do repositório) `CLAUDE.md` | Parte fixa, revisão 1.2 (acréscimo em §6.3 aprendido neste experimento) |
| `relatorios-do-agente.md` | Transcrição literal: desenvolvedor (3 turnos), revisor independente, mensagens do revisor humano |
| `antes/` · `depois/` | Os 4 arquivos da tarefa antes e depois dos ajustes A1–A6 |
| `*.antes-depois.diff` | Diffs unificados antes → depois de `envcheck.py`, `test_envcheck.py`, `test_cli.py` |
| `tarefa-002.patch` | Patch final (aplicar sobre `main` **depois** de `experimento-001/tarefa-001.patch`, que repara `tests/test_schemas.py`) |
| `verificacao-independente.py` | Script que executa os 13 exemplos do contrato pela CLI real (rodar na raiz do repositório) |

Aplicação no repositório real (validada sobre `main@4d520f9`: 4 checks verdes, 239 testes):

```bash
git apply extra/experimento-001/tarefa-001.patch   # se ainda não aplicado
git apply extra/experimento-002/tarefa-002.patch
ruff check . && ruff format --check . && mypy src && pytest
```
