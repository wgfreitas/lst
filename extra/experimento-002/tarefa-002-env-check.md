# TAREFA — `lst env-check`: conferir o `.env` local contra o contrato `.env.example` sem expor valores

**Tipo:** implementar
**Tamanho-alvo:** 1 módulo novo (`src/lst/envcheck.py`) + 1 subcomando aditivo em `cli.py` · cabe em 1 sessão

## Contexto da tarefa

- Para que existe: o projeto já teve `.env` com variáveis mortas (`LST_HTTP_TIMEOUT`,
  `LST_MAX_FLAGGED_EVENTS`) sendo ignoradas em silêncio, e dois incidentes de vazamento de chave
  causados por imprimir o `.env` no terminal. Falta uma automação local que diga "seu `.env` está
  coerente com o contrato?" **sem nunca mostrar os valores**.
- Quem chama / de onde vem a entrada: o analista, via `lst env-check`, na raiz do projeto. As
  entradas são dois arquivos-texto: `.env.example` (o contrato, versionado) e `.env` (local, com
  segredos). Ambos são entrada externa — podem estar malformados.
- Módulos-alvo e testes espelhados: `src/lst/envcheck.py` (lógica, pura) e `src/lst/cli.py`
  (subcomando fino); `tests/test_envcheck.py` (novo) e `tests/test_cli.py` (2–3 testes do subcomando).
- Código vizinho a imitar: `cli.py` (comando `scan`: help em pt-BR, mensagens de erro em pt-BR,
  exit codes 0/1/2, `typer.echo(..., err=True)` para erros); `config.py` (tabela de aliases
  `AliasChoices("LLM_X", "OLLAMA_X")`); `schemas.py` (`StrEnum` para categorias).
- Decisões já tomadas que se aplicam: nomes das 8 variáveis e dos 3 aliases legados
  (`config.Settings`); `pydantic-settings` lê chaves sem distinção de maiúsculas; `Settings`
  rejeita string vazia (`min_length=1`) e valores fora de faixa — validar tipos/faixas é papel
  dele, não desta ferramenta.

## Contrato

### Regras de parsing (uma única função, usada nos dois arquivos)
1. Linhas em branco e linhas cujo primeiro caractere não-branco é `#` são ignoradas.
2. Prefixo opcional `export ` é aceito e descartado.
3. Linha válida é `CHAVE=valor`: `CHAVE` casa `[A-Za-z_][A-Za-z0-9_]*`; `valor` é tudo após o
   primeiro `=`, com espaços das pontas removidos e um par de aspas envolventes (`"` ou `'`)
   removido.
4. Linha que não casa (sem `=`, chave inválida) é **malformada**: registrada apenas pelo número
   da linha — nunca pelo conteúdo, que pode ser um segredo colado sem chave.
5. Chaves são comparadas sem distinção de maiúsculas; a grafia original é preservada para exibição.
6. Chave repetida no mesmo arquivo: a última ocorrência vale (semântica dotenv) e gera achado
   `duplicate` com as linhas envolvidas.

### Regras do contrato (a partir do `.env.example`)
7. Toda chave do `.env.example` é conhecida. Chave com valor vazio no example é **obrigatória**;
   com valor preenchido é **opcional** (tem default no `Settings`).
8. Aliases legados (tabela fixa no módulo, espelhando `config.Settings`): `OLLAMA_API_KEY` →
   `LLM_API_KEY`, `OLLAMA_MODEL` → `LLM_MODEL`, `OLLAMA_BASE_URL` → `LLM_BASE_URL`. Um alias
   presente satisfaz a chave canônica e gera achado `legacy`.

### Achados (cada um com tipo, chave ou linha, e severidade)
- `missing` (erro): chave obrigatória ausente, ou presente com valor vazio, considerando aliases.
- `empty` (erro): chave opcional presente com valor vazio — `Settings` rejeita string vazia.
- `unknown` (aviso): chave do `.env` que não é conhecida nem alias (ex.: `LST_HTTP_TIMEOUT`).
- `legacy` (aviso): alias legado em uso.
- `duplicate` (aviso): chave repetida no mesmo arquivo.
- `malformed` (aviso): linha malformada — só o número da linha.

### Saída
- Função pura: `check_env(example_text: str, env_text: str) -> EnvReport`, onde `EnvReport` é
  imutável (`dataclass(frozen=True)`; não é contrato entre estágios do pipeline, então não usa
  pydantic), com os achados, o número de chaves do contrato conferidas e uma propriedade `ok`
  (verdadeira quando não há achado de severidade erro).
- Subcomando: `lst env-check [--env PATH] [--example PATH]` (padrões: `.env` e `.env.example` no
  diretório atual). Imprime em pt-BR uma linha por achado, **sem valores**, e uma linha final de
  resumo. Formato de referência:
  `[ERRO] LLM_API_KEY: obrigatória e ausente` ·
  `[AVISO] LST_HTTP_TIMEOUT: chave desconhecida (linha 17)` ·
  `[AVISO] OLLAMA_API_KEY: nome legado — prefira LLM_API_KEY` ·
  `[AVISO] linha 9: malformada (ignorada)` ·
  resumo: `OK: 8 chaves conferidas, sem problemas` ou `2 erro(s), 1 aviso(s)`.
- Exit codes (mesma semântica do `scan`): `0` sem erros (avisos permitidos); `1` com ≥ 1 erro;
  `2` `.env` ou `.env.example` inexistente, com `Erro: arquivo não encontrado: <path>` em stderr.
- Erros: nenhuma exceção escapa para o analista; nenhum `except Exception` silencioso; linha
  malformada não é exceção, é achado.

## Exemplos que definem o contrato

Normal:
- **N1** example = o `.env.example` real do repositório; `.env` com as 8 chaves `LLM_*`
  preenchidas (valores `fake-…`) → nenhum achado; `OK: 8 chaves conferidas, sem problemas`; exit 0.
- **N2** `.env` só com `OLLAMA_API_KEY=fake-key`, `OLLAMA_MODEL=fake-model`,
  `OLLAMA_BASE_URL=http://fake` → 3 achados `legacy`, 0 erros; exit 0.

Limite:
- **L1** `LLM_API_KEY=` (vazio) → 1 `missing` (erro); exit 1.
- **L2** `.env` válido mais a linha `LST_HTTP_TIMEOUT=30` → 1 `unknown` (aviso) com a linha; exit 0.
- **L3** `export LLM_MODEL="fake-model"` → reconhecida (prefixo e aspas), nenhum achado.
- **L4** `LLM_MODEL=` (opcional vazia) → 1 `empty` (erro); exit 1.
- **L5** `LLM_API_KEY` em duas linhas → 1 `duplicate` (aviso) citando as duas linhas; a última vale.
- **L6** `.env` vazio (0 bytes) → exatamente 1 `missing` (só `LLM_API_KEY` é obrigatória); exit 1.
- **L7** `llm_api_key=fake-key` (minúsculas) → reconhecida; nenhum achado.

Erro:
- **E1** `.env` inexistente → `Erro: arquivo não encontrado: .env` (stderr); exit 2.
- **E2** `.env.example` inexistente → idem para o example; exit 2.
- **E3** linha `fake-secret-without-key` (sem `=`) → 1 `malformed` (aviso) com o número da linha;
  a string `fake-secret-without-key` NÃO aparece em stdout nem em stderr.
- **E4** (segredos) para qualquer entrada, nenhum valor do `.env` aparece na saída: teste com o
  valor sentinela `VALOR-QUE-NAO-PODE-VAZAR` em todas as chaves.

## Critérios de Clean Code desta tarefa (além das convenções do CLAUDE.md §3.3–3.4)

- **Nomes dizem o que representam sem ler a implementação:** `EnvReport`, `EnvFinding`,
  `FindingKind` (`StrEnum`, como as categorias do projeto), `Severity`-like só se não colidir com
  `schemas.Severity` (usar `FindingSeverity`), `parse_dotenv`, `check_env`, `render_report`.
  Proibidos: `data`, `result`, `tmp`, `info`, `obj`, `process`, `handle`, `helper`, `util`.
  Booleanos leem como perguntas (`is_required`).
- **Uma responsabilidade por função:** (a) parse de texto dotenv → estrutura; (b) comparação
  contrato × env → achados; (c) render dos achados → texto pt-BR; (d) CLI: paths, leitura dos
  arquivos, exit codes. Nenhuma função lê arquivo E decide E imprime. (a)–(c) são puras.
- **Comentários explicam decisões, nunca repetem o código:** por que nunca imprimir valores; por
  que linha malformada é só número; por que os aliases existem; docstring de módulo com
  "Design rules enforced here" (como nos outros módulos).
- **Erros visíveis e compreensíveis:** mensagens pt-BR no padrão do `scan`; nada de `None`/`-1`
  para sinalizar falha; nada de `except Exception`.
- **Sem duplicação:** um parser para os dois arquivos; nomes das chaves e aliases em UMA tabela;
  nenhuma string de chave repetida em lugares diferentes.
- **Validação na fronteira:** o texto dos arquivos é entrada externa — todo formato inesperado
  vira achado ou erro visível, nunca traceback.
- **Segredos:** nenhum valor real em código, teste ou fixture; valores de teste com prefixo
  `fake-`; a saída nunca contém valores (E4 garante).
- **Dependências:** stdlib + `typer` (já presente). NÃO importar `dotenv`: está instalado só como
  dependência transitiva de `pydantic-settings` e não é declarada no `pyproject.toml`. Nada novo
  no `pyproject.toml`.
- **Tamanho não é critério:** sem meta de linhas; não fragmentar em funções de uma linha; não
  otimizar nada.
- **Rastreabilidade:** cada teste novo carrega o ID do caso no nome (`test_n1_…`, `test_l3_…`,
  `test_e4_…`); um teste sem ID de caso é suspeito.

## Fora de escopo desta tarefa

- Validar tipos e faixas dos valores (papel do `Settings`); conectar ao provedor; gerar ou editar
  o `.env`; alterar `scan`/`version` ou seus exit codes; README/docs/CHANGELOG (listar pendências).

## Critérios de aceitação (verificáveis)

- [ ] Testes para todos os casos N1–N2, L1–L7, E1–E4, com o ID no nome.
- [ ] Os 4 checks verdes na suíte completa; contagem 207 → 207 + novos.
- [ ] Contratos públicos existentes intocados (`scan`, `version`, exit codes, env vars).
- [ ] `grep -n "import dotenv\|from dotenv" src/` vazio; `pyproject.toml` sem diff.
- [ ] Docs: pendência listada (README EN+PT, `docs/usage.md`), não editar.

## Gates pré-autorizados nesta tarefa

- `aprovado: novo subcomando aditivo lst env-check em cli.py` (não altera `scan`/`version`).
- Nova dependência: NÃO autorizada.

---

## Esclarecimentos do contrato — revisão 2 (após a leitura crítica e a revisão)

A leitura crítica comparou o parser com o `python-dotenv` que o `Settings` usa de fato (executando
a biblioteca) e encontrou formas comuns em que a ferramenta contradiria o `Settings`: falso ERRO em
`CHAVE = valor` (espaço antes do `=`), em `export<TAB>CHAVE=valor` e em arquivo com BOM UTF-8;
falso OK em aspa não fechada (`CHAVE="valor`) e em `CHAVE="" # comentário`. As regras 2 e 3 eram
mais estritas que o leitor real sem que isso fosse intenção. Ficam **esclarecidas** assim (o
restante do contrato não muda; os exemplos N1–N2, L1–L7 e E1–E4 continuam valendo byte a byte):

- **Regra 2 (esclarecida):** o prefixo é `export` seguido de um ou mais espaços ou tabs.
- **Regra 3 (esclarecida):** espaços/tabs são permitidos entre a chave e o `=` e entre o `=` e o
  valor. Um BOM UTF-8 (`﻿`) no início do texto é descartado, como faz o `python-dotenv`.
  Valor **entre aspas** (`"` ou `'`): a aspa de fechamento deve estar na mesma linha; o valor é o
  miolo (pode ser vazio); depois da aspa de fechamento só pode haver espaços ou um comentário
  `#…` — qualquer outra coisa, ou aspa não fechada, torna a linha **malformada** (só o número da
  linha, como na regra 4). Valor **sem aspas**: tudo após o `=`, com as pontas removidas, sem
  tratar comentário inline (`CHAVE=x # c` e `CHAVE= # c` são não-vazios tanto aqui quanto no
  `python-dotenv`; para presença/vazio não há diferença observável, e o tipo/faixa é papel do
  `Settings`).
- **Fora de escopo (novo):** valores multilinha entre aspas (`CHAVE="a\nb"`) — o `python-dotenv`
  aceita; aqui as linhas viram `malformed` (visível, nunca silencioso). Nenhuma das 8 variáveis
  do projeto admite valor multilinha.

Exemplos adicionais que passam a definir o contrato:

- **L8** `LLM_API_KEY = fake-key` (espaços em volta do `=`) → reconhecida; nenhum achado; exit 0.
- **L9** texto iniciado por BOM + `LLM_API_KEY=fake-key` → reconhecida; nenhum achado.
- **L10** `LLM_MODEL="fake-model" # comentário` → reconhecida (valor entre aspas + comentário);
  nenhum achado.
- **E5** `LLM_API_KEY="fake-key` (aspa não fechada) → 1 `malformed` (aviso, só o número da linha)
  e 1 `missing` (erro, ausente); exit 1; `fake-key` nunca aparece na saída.
- **E6** `LLM_API_KEY="" # preencha` → 1 `missing` (erro, vazia, com a linha); exit 1.

Critério de aceitação adicional: os casos acima foram conferidos contra `Settings(_env_file=…)`
real (carrega / rejeita) e a ferramenta deve concordar com ele em todos.
