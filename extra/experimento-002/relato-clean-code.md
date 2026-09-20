# Clean Code na prática — agente desenvolvedor do LST, tarefa 002 (`lst env-check`)

## 1. O problema

O LST lê sua configuração de um `.env` (via `pydantic-settings`), e dois incidentes reais
motivaram a tarefa: variáveis mortas no `.env` (`LST_HTTP_TIMEOUT`, `LST_MAX_FLAGGED_EVENTS`)
ignoradas em silêncio, e chaves de API vazadas ao imprimir o `.env` no terminal. Faltava uma
automação local que respondesse "meu `.env` está coerente com o contrato?" **sem nunca mostrar
valores**. Escolhi um problema pequeno, mas com regras que cabem numa página:

- **Entradas:** dois arquivos-texto — `.env.example` (o contrato, versionado; valor vazio =
  variável obrigatória, valor preenchido = opcional) e `.env` (local, com segredos). Ambos são
  entrada externa e podem estar malformados.
- **Saída:** uma função pura `check_env(example_text, env_text) -> EnvReport` (dataclass
  imutável com achados, contagem de chaves conferidas e `ok`) e o subcomando aditivo
  `lst env-check [--env PATH] [--example PATH]`, que imprime uma linha pt-BR por achado — só nome
  da chave e número da linha — e um resumo; exit `0` sem erros, `1` com erro, `2` arquivo
  inexistente/ilegível (mensagem em stderr).
- **Regras:** parsing dotenv (linhas em branco e `#` ignoradas; `export` opcional; `CHAVE=valor`
  com aspas envolventes removidas; linha inválida registrada **só pelo número**, porque pode ser
  um segredo colado sem chave; chaves sem distinção de maiúsculas; duplicata: a última vale);
  seis tipos de achado (`missing` e `empty` são erros; `unknown`, `legacy`, `duplicate` e
  `malformed` são avisos); os três aliases legados `OLLAMA_*` satisfazem a chave canônica com
  aviso, espelhando o `AliasChoices` do `Settings`.
- **Exemplos** que definem o contrato: 2 normais (N1 `.env` completo → `OK: 8 chaves
  conferidas, sem problemas`; N2 só aliases `OLLAMA_*` → 3 avisos, exit 0), 7 de limite (L1
  obrigatória vazia; L2 chave desconhecida com linha; L3 `export` + aspas; L4 opcional vazia →
  erro, porque o `Settings` rejeita string vazia; L5 duplicata citando as duas linhas; L6 `.env`
  de 0 bytes → exatamente 1 erro; L7 chave em minúsculas) e 4 de erro (E1/E2 arquivos
  inexistentes → exit 2; E3 linha sem `=` → aviso só com o número, e o conteúdo
  `fake-secret-without-key` nunca aparece; E4 sentinela `VALOR-QUE-NAO-PODE-VAZAR` em todas as
  chaves → nunca aparece em stdout/stderr). A especificação completa está em
  `tarefa-002-env-check.md`.

## 2. Como orientei a geração

A parte fixa foi o `CLAUDE.md` (rev. 1.1) do exercício anterior — papel, regras R1–R10,
protocolo de lacunas N1/N2/N3, passo de linha de base. A parte variável foi o arquivo da tarefa,
que em vez de pedir "código limpo" explicitou o que eu esperava:

| Critério | O que a tarefa exigiu, concretamente |
|---|---|
| Nomes | `EnvReport`, `EnvFinding`, `FindingKind` (`StrEnum`, como as categorias do projeto), `FindingSeverity` (para não colidir com `schemas.Severity`), `parse_dotenv`, `check_env`, `render_report`; booleanos como perguntas (`is_required`); **proibidos** `data`, `result`, `tmp`, `info`, `obj`, `process`, `handle`, `helper`, `util` |
| Responsabilidade | quatro papéis separados — (a) parse texto → estrutura, (b) contrato × env → achados, (c) achados → texto pt-BR, (d) CLI: paths, leitura, exit codes; "nenhuma função lê arquivo E decide E imprime"; (a)–(c) puras |
| Comentários | explicam decisões, nunca repetem o código: por que nunca imprimir valores, por que a linha malformada é só número, por que os aliases existem; docstring de módulo com "Design rules enforced here", como nos outros módulos |
| Erros | mensagens pt-BR no padrão do `scan`; nada de `None`/`-1` como sinal de falha; nada de `except Exception`; linha malformada é achado, não exceção |
| Duplicação | um parser para os dois arquivos; nomes de chaves e aliases em uma única tabela |
| Fronteira | o texto dos arquivos é entrada externa — todo formato inesperado vira achado ou erro visível, nunca traceback |
| Segredos | valores de teste com prefixo `fake-`; a saída nunca contém valores (E4 garante) |
| Dependências | stdlib + `typer`; **não** importar `dotenv` (instalado só como dependência transitiva do `pydantic-settings`, não declarada no `pyproject.toml`); nada novo no `pyproject.toml` |
| Tamanho | "não é critério: sem meta de linhas; não fragmentar em funções de uma linha; não otimizar" |
| Rastreabilidade | cada teste carrega o ID do caso no nome (`test_l3_…`, `test_e4_…`) |

Gate pré-autorizado: o subcomando aditivo em `cli.py`. Nova dependência: não autorizada.

## 3. O que o agente produziu

Após rodar a linha de base (207 testes verdes), o agente escreveu 17 testes antes de qualquer
implementação (vermelhos por `ModuleNotFoundError`), depois o módulo `envcheck.py` (459 linhas,
stdlib apenas), o subcomando e 6 testes de CLI — 23 testes novos, 207 → 230, os quatro checks
verdes, `pyproject.toml` intocado, nenhum `import dotenv`. Todos os 13 exemplos passaram quando
eu os executei pela CLI real. O agente declarou dez suposições e três decisões N2 com default
adotado, sendo a terceira a mais importante para o que veio depois: "o parser é mais estrito que
o `python-dotenv` usado pelo `Settings`" — e nela ele afirmou que o único caso com "OK" falso
seria `KEY= # comentário`, "que o dotenv lê como vazio".

## 4. Minha leitura crítica (antes de pedir a revisão)

Percorri o checklist — nomes, propósito, comentários, erros, duplicação, validação de entradas,
segredos, dependências — e executei o que não dava para julgar lendo:

| # | Achado | Como cheguei |
|---|---|---|
| H1 | **Segredos.** O parser devolve os valores no tipo público `ParsedDotenv`: `repr(parse_dotenv("LLM_API_KEY=VALOR-QUE-NAO-PODE-VAZAR"))` imprime a sentinela. O checker só usa `is_empty`; a docstring do atributo admite "kept only so the checker can test for emptiness". A regra do módulo ("values never leave the parser") era declarada, não estrutural | executei o `repr` |
| H2 | **Fronteira / correção.** O parser diverge do leitor real: `LLM_API_KEY = fake` (espaços), `export<TAB>KEY=v` e arquivo com BOM viram **falso erro** (exit 1) enquanto o `Settings` carrega; `KEY='fake"` (aspas trocadas) vira **falso OK** enquanto o dotenv rejeita. E a análise do agente estava errada no caso que ele citou: executei `dotenv_values` e `KEY= # c` é lido como `# c`, não vazio — nesse caso a ferramenta já concordava | executei `dotenv_values` sobre 13 formas |
| H3 | **Erros visíveis.** `_describe` chega ao ramo `duplicate` por eliminação (último `return` sem `if`): um `FindingKind` novo seria impresso como "chave repetida" em silêncio | leitura |
| H4 | **Nomes.** `_parse_findings` lê como verbo ("parse os achados"); são achados *oriundos* do parsing | leitura |
| H5 | **Nomes.** Constantes `_IN_EXAMPLE_FILE_PT = " no arquivo de exemplo"` com espaço inicial: fragmentos de frase são ilegíveis isolados | leitura |
| H6 | **Testes.** `test_l5_…_in_example_file` fixa o literal `14` (linha de `LLM_MODEL` no `.env.example` real): um comentário a mais no example quebra o teste sem regra alguma mudar | leitura |
| H7 | Fuzz de 5.000 textos aleatórios sem exceção; diretório passado como `--env` dá "arquivo não encontrado" (impreciso, mas visível); contrato sem chaves dá `OK: 0 chaves conferidas` (verdadeiro) — nada a mudar | executei |

## 5. A revisão do agente revisor

Um segundo agente, sem acesso ao relatório do desenvolvedor nem às minhas anotações, recebeu a
tarefa, as convenções do projeto e o código, com a instrução de classificar e justificar. Ele
trouxe 9 apontamentos, cada um com localização, evidência executada e sugestão:

| Classe | Apontamento (resumo) | Relação com a minha leitura |
|---|---|---|
| [bloqueia] R1 | espaço/tab antes do `=` → falso erro; `Settings` carrega | = H2 |
| [bloqueia] R2 | BOM UTF-8 → falso erro; o dotenv faz `removeprefix("﻿")` | = H2 |
| [bloqueia] R3 | aspa não fechada (`KEY="x`) e `KEY="" # c` → **falso OK**; `Settings` rejeita ambos | H2 achou o falso OK só nas aspas trocadas; o caso `"" # comentário` **eu não tinha visto** |
| [bloqueia] R4 | `DotenvEntry.value` retém o segredo; `repr` o imprime; sugestão mínima `field(repr=False)`, melhor `is_empty: bool` | = H1, mesma evidência |
| [melhora] R5 | `_describe` chega a `DUPLICATE` por eliminação; `match` + `assert_never` verificável pelo mypy | = H3 |
| [melhora] R6 | testes acoplados a detalhes que não são regra: default `gpt-oss:20b`, literal `14`, ordem exata dos achados em E4 | ⊃ H6 (achou dois acoplamentos a mais) |
| [melhora] R7 | regras sem assert direto: grafia preservada na saída (regra 5), resumo misto `N erro(s), M aviso(s)`, `--help` sem `env-check` | não vi |
| [estilo] R8 | renomear `_parse_findings` → `_findings_from_parsing` | = H4 (eu tinha como melhora) |
| [estilo] R9 | mover sentinela/caminho/chaves para `tests/conftest.py` | não vi; rejeitei (§6) |

O revisor não levantou H5 (fragmentos com espaço inicial), e classificou como "lacuna preenchida
sem ser declarada" algo que o desenvolvedor *tinha* declarado (N2 #3) — a imprecisão é
compreensível, ele não viu o relatório; mas o ponto que fica é outro: **declarar uma suposição não
a torna correta**. O desenvolvedor declarou a estritez, errou o diagnóstico de qual caso
importava, e só a execução da biblioteca real (por mim e pelo revisor, de forma independente)
mostrou onde a ferramenta contradizia o `Settings`.

## 6. Comparação, ambiguidade esclarecida e ajustes solicitados

R1–R3/H2 não eram erro do agente: eram **ambiguidade da minha especificação**. As regras 2 e 3
descreviam um formato literal (`export ` com um espaço; `CHAVE=valor` sem espaços) quando a
intenção era "o que o `Settings` lê". Antes de pedir qualquer ajuste, esclareci o contrato numa
revisão 2 da tarefa: `export` seguido de um ou mais espaços/tabs; espaços/tabs permitidos em
volta do `=`; BOM inicial descartado; valor entre aspas deve fechar na mesma linha e só pode ser
seguido de espaços ou `#…`, senão a linha é malformada; valor sem aspas continua literal
(comentário inline não faz diferença observável para presença/vazio, e tipo/faixa é papel do
`Settings`); valores multilinha ficam fora de escopo, visíveis como `malformed`. Cinco exemplos
novos (L8 espaços, L9 BOM, L10 aspas + comentário, E5 aspa não fechada, E6 `"" # comentário`) e
um critério de aceitação novo: a ferramenta deve concordar com `Settings(_env_file=…)` real em
todos eles. Só então enviei ao desenvolvedor o pedido de ajustes (Template 7 da unidade), com a
lista fechada e as rejeições justificadas:

| Ajuste | Decisão | Por quê |
|---|---|---|
| A1 = R1+R2+R3 (parser conforme regras esclarecidas) | **aceito** | corrigem falsos erros e dois falsos OK — o pior resultado para uma ferramenta em que o analista confia; testes primeiro (L8–L10, E5–E6) |
| A2 = R4/H1 (`value` → `is_empty`) | **aceito na forma "menor privilégio"**, não o `repr=False` mínimo | `repr=False` esconde; `is_empty` elimina: nenhum objeto do módulo consegue mais conter um segredo, e a docstring passa a ser verdadeira por construção |
| A3 = R5/H3 + H5 | **aceito, ampliado** | `match` exaustivo com `assert_never`; na mesma edição, montar a frase "no/do arquivo de exemplo" no ponto de uso e eliminar os fragmentos com espaço inicial |
| A4 = R6/H6 | **aceito** | contrato sintético nos testes "no arquivo de exemplo"; `is_empty is False` em vez do default `gpt-oss:20b`; E4 compara os tipos como multiconjunto, porque a ordem não faz parte de E4 |
| A5 = R7 | **adaptado** | os dois asserts de regra sim; o `--help`, porém, num teste **novo** em vez de editar `test_cli_help_lists_commands` — o revisor dizia que acrescentar um assert não fere R4, e tem razão na letra, mas não quis abrir a discussão: R4 vale melhor sem exceções |
| A6 = R8/H4 | **aceito** | renomear é barato e o nome novo diz o que a função devolve |
| R9 (consolidar dados de teste em `conftest.py`) | **rejeitado** | os dois arquivos testam camadas diferentes e ficam legíveis sozinhos; `_FULL_ENV` do `test_cli.py` usa de propósito valores não numéricos (`fake-timeout`) para mostrar que a CLI não valida tipos; reduzir linhas editando um arquivo compartilhado não é melhoria |
| N2 #1 (achados também no `.env.example`) e N2 #2 (arquivo ilegível → exit 2) | **mantidos** | coerentes com "todo formato inesperado vira achado ou erro visível" |

O agente aplicou exatamente a lista, registrou os testes novos vermelhos antes de tocar no módulo
(`7 failed, 31 passed` → `38 passed`) e fez uma observação honesta que eu não teria pedido: L10 já
passava no parser antigo "por acaso" (a linha era aceita como valor sem aspas); quem distingue o
comportamento novo é E6. Ele também deixou um residual declarado (aspas escapadas `\"` dentro
de valor com aspas — o dotenv aceita, aqui vira `malformed`, visível), que aceitei como limitação.

## 7. Antes e depois

**(a) Segredo retido vs. só o fato necessário** — `DotenvEntry`:

```python
# antes
key: str
value: str          # "Kept only so the checker can test for emptiness; it is never rendered."
lines: tuple[int, ...]
@property
def is_empty(self) -> bool:
    return self.value == ""

# depois — "The value itself is dropped by the parser: only whether it is empty survives"
key: str
is_empty: bool
lines: tuple[int, ...]
```

`repr(parse_dotenv(...))` contém a sentinela: **True → False**.

**(b) Parser literal vs. parser que concorda com o leitor real:**

```python
# antes
_EXPORT_PREFIX: Final = "export "
_KEY_VALUE_RE: Final = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)")
...
value = _strip_enclosing_quotes(matched.group("value").strip())

# depois
_KEY_VALUE_RE: Final = re.compile(
    # Optional `export` keyword, the key, then `=` with spaces/tabs allowed around it.
    r"(?:export[ \t]+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*"
    # Either a quoted value closed on the same line, followed only by spaces or a comment...
    r"(?:(?:\"(?P<double_quoted>[^\"]*)\"|'(?P<single_quoted>[^']*)')[ \t]*(?:#.*)?"
    # ...or an unquoted value: everything up to the end of the line, `#` included.
    r"|(?P<unquoted>(?![\"']).*))"
)
...
# A BOM is not whitespace for str.strip(); dropping it mirrors python-dotenv.
text = text.removeprefix(_UTF8_BOM)
```

**(c) Ramo por eliminação vs. exaustividade verificada pelo tipo** — `_describe`:

```python
# antes
if finding.kind is FindingKind.LEGACY:
    ...
in_file = _IN_EXAMPLE_FILE_PT if is_in_example else ""          # " no arquivo de exemplo"
return f"{finding.key}: chave repetida{in_file} ({where}) — a última vale"

# depois
match finding.kind:
    case FindingKind.MISSING: ...
    ...
    case FindingKind.DUPLICATE:
        if is_in_example:
            return (f"{finding.key}: chave repetida no {_EXAMPLE_FILE_LABEL_PT} ({where})"
                    " — a última vale")
        return f"{finding.key}: chave repetida ({where}) — a última vale"
    case FindingKind.MALFORMED: ...
    case _:
        assert_never(finding.kind)
```

**(d) Teste acoplado ao arquivo real vs. contrato sintético:**

```python
# antes
first_appended_line = example_text.count("\n") + 1
contract_with_duplicate = example_text + "LLM_MODEL=\nLLM_MODEL=fake-model\n"
assert finding.lines == (14, first_appended_line, first_appended_line + 1)

# depois
contract_with_duplicate = "LLM_API_KEY=\nLLM_MODEL=\nLLM_MODEL=fake-model\n"
assert finding.lines == (2, 3)
assert report.checked_key_count == 2
```

Nenhuma mensagem de saída mudou; os 13 exemplos originais continuam valendo byte a byte. O
módulo **cresceu** (459 → 494 linhas) e ganhou uma função (`_is_empty_value`); os testes foram de
17 para 25. Nada disso é a evidência da melhoria — a evidência está na tabela a seguir.

## 8. Verificações

| Verificação | Antes dos ajustes (rev. 1) | Depois (rev. 2) |
|---|---|---|
| Os 4 checks, rodados por mim na suíte completa | `All checks passed!` · `61 files already formatted` · `mypy: no issues in 30 files` · `230 passed` (97,18%) | idem · `239 passed` (96,80% — as 2 linhas sem cobertura são o guard de invariante e o `assert_never`, inatingíveis) |
| 13 exemplos do contrato executados pela CLI real (`verificacao-independente.py`) | 13/13 | 13/13 + L8–L10, E5–E6 5/5, sem vazar `fake-key` |
| Concordância com `Settings(_env_file=…)` real, em 24 formas de escrever o `.env` (meu conjunto, independente do do agente) | **16/24** — 4 falsos erros (espaços ou tabs em volta do `=`, tab após `export`, BOM) e 4 falsos OK (aspa não fechada, lixo após a aspa de fechamento, `"" # c`, aspas trocadas) | **24/24** |
| Fuzz: 5.000 textos aleatórios como `.env` e como contrato | nenhuma exceção | nenhuma exceção |
| `repr(parse_dotenv(...))` contém a sentinela | True | **False** |
| Mutação 1 — remover o descarte do BOM | — | só `test_l9` falha |
| Mutação 2 — remover o lookahead que separa aspas de valor sem aspas | — | só os dois `test_e5` falham (o falso OK voltaria) |
| Mutação 3 — `_is_empty_value` sempre `False` | — | 11 testes falham (L1, L4, L6, E6, N2-alias-vazio, CLI-L1…) |
| Mutação 4 — proibir espaços em volta do `=` | — | só `test_l8` falha |
| Mutação 5 — renderizar `duplicate` com o texto de `missing` | — | só `test_l5` falha |
| Revisão dos testes: regra × implementação | 3 acoplamentos a detalhe (default do modelo, linha 14, ordem em E4) | removidos; 3 regras sem assert direto ganharam teste; nenhum assert sobre o regex |
| Estado do repositório | `HEAD` inalterado, zero commits, só os 4 arquivos da tarefa, `pyproject.toml` sem diff, `grep dotenv src/` vazio, sem bytes de BOM crus nos fontes | idem |
| Patch aplicado sobre o `main@4d520f9` real (+ o patch da tarefa 001) | — | 4 checks verdes, `239 passed` |

**Decisão: aceitar** (um commit, mensagem sugerida pelo agente em `relatorios-do-agente.md`).

## 9. Comentários

**Quais orientações ajudaram o agente a produzir uma solução mais compreensível?** As que
davam algo verificável em vez de um adjetivo. A lista de nomes proibidos e os nomes esperados
produziram um módulo que se lê sem abrir a implementação (`FindingKind.MALFORMED`,
`checked_key_count`, `is_duplicated`), e o agente estendeu a convenção sozinho (`DotenvEntry`,
`CheckedFile`). A separação em quatro papéis virou três funções puras mais um subcomando cujo corpo
tem cinco instruções — o `env_check` do `cli.py` lê os dois arquivos, chama `check_env`, imprime
e sai, e nada mais. "Comentários
explicam decisões" gerou a docstring "Design rules enforced here", que foi o texto que mais me
ajudou na revisão — inclusive para pegá-la em contradição (H1). "Tamanho não é critério"
evitou a fragmentação que costumo ver em código gerado: nenhuma função foi extraída para
encurtar outra, e a única de uma linha (`_normalise_key`) existe para dar nome a uma decisão —
comparação sem distinção de maiúsculas — usada em oito pontos do módulo. A regra de segredos com sentinela deu ao agente e a mim o mesmo teste
de aceitação. E o passo de linha de base do `CLAUDE.md`, herdado do experimento anterior, custou
um comando e deu o ponto de comparação.

O que **não** ajudou foi a minha própria regra 3, escrita como formato literal. Um agente que
obedece à letra fez exatamente o que pedi, e o resultado contradizia o programa que a ferramenta
existe para prever. A lição não é sobre o agente: "regras bem definidas" precisam ser definidas
em relação ao consumidor real (`Settings`), e a única verificação que resolveu isso foi executar
a biblioteca — nem a leitura do código, nem a suposição declarada pelo agente, nem a minha
memória de como o dotenv funciona (eu também errei sobre `KEY= # c`).

**Sugestões aceitas, adaptadas ou rejeitadas** estão na tabela do §6. O padrão: aceitei tudo
que veio com evidência executada (R1–R4) ou que tornava um risco visível (R5); adaptei quando a
letra de uma regra minha (R4 do `CLAUDE.md`) valia mais que a economia de um teste; rejeitei a
única sugestão cujo ganho era reduzir linhas (R9). Sobre "reduzir linhas ou criar mais funções
não é evidência de melhoria": a solução final é maior e tem uma função a mais, e é melhor —
porque a tabela de concordância foi de 16/24 para 24/24, porque o `repr` deixou de vazar e
porque cinco mutações provam que os testes novos reagem. Se eu tivesse aceitado R9, o diff seria
menor e nada disso mudaria.

Como no experimento anterior, a lição virou texto na parte fixa: o `CLAUDE.md` passou à
revisão 1.2 com um acréscimo no passo "Lacunas" — toda suposição sobre como uma biblioteca ou
sistema vizinho se comporta é verificada executando-a, com comando e resultado no relatório,
nunca presumida.

**Limitações.** Uma execução, em sandbox, com subagentes (não o Claude Code no meu ambiente); o
revisor foi um agente da mesma família do desenvolvedor, o que pode correlacionar pontos cegos —
por isso a minha leitura veio antes e ficou registrada separada. O residual das aspas escapadas
ficou declarado, não resolvido.

## 10. Reflexão: e na equipe?

O critério que eu incorporaria à geração e à revisão de código é o que decidiu este exercício:
**toda afirmação sobre como uma biblioteca ou sistema vizinho se comporta tem de ser executada,
não lida** — e a revisão precisa dizer onde (arquivo, linha), por que (critério ou evidência) e
com que peso (`[bloqueia]`, `[melhora]`, `[estilo]`). Na equipe, mantemos ferramentas Python de
automação sobre o parque Linux, e quase todas dependem de um vizinho que "todo mundo sabe como
funciona": o formato de saída de um comando, o parser de um arquivo de configuração, a API de um
serviço. É exatamente ali que um agente (ou um colega) produz uma suposição plausível e errada —
como a do `KEY= # c` — e é ali que um "OK" falso custa mais do que um erro visível.

O que precisaria mudar na rotina é pouco e concreto: (1) cada tarefa entregue a um agente nasce
com um arquivo de uma página — entradas, saídas, regras e exemplos normal/limite/erro, versionado
junto com o código —, e qualquer regra sobre um sistema vizinho vem acompanhada de um exemplo
**executado contra ele**, não descrito; (2) a revisão passa a ter as três classes como campo
obrigatório no template de pull request, com localização e justificativa, e um `[bloqueia]` sem
evidência executada não bloqueia; (3) quem revisa não é quem gerou — se foi um agente, a
primeira leitura é humana e a segunda é de outro agente que não viu o relatório do primeiro; (4)
o "pronto" inclui rodar os exemplos da especificação e, quando o risco justificar, uma mutação
simples que mostre que os testes reagem. O custo é uma hora a mais por tarefa pequena. O que
compramos com ela, neste exercício, foram dois falsos OK que teriam saído em produção com os
quatro checks verdes e 100% de cobertura.
