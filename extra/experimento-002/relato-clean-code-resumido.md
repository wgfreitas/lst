# Clean Code na prática — agente desenvolvedor do LST

## O problema

O LST lê sua configuração de um arquivo `.env`. Dois problemas reais motivaram a tarefa:
variáveis antigas que ficavam no arquivo sendo ignoradas em silêncio, e chaves de API vazadas
quando alguém imprimia o `.env` no terminal. Pedi ao agente um subcomando novo, `lst env-check`,
que compara o `.env` com o modelo versionado (`.env.example`) e diz se está coerente — **sem
nunca mostrar os valores**, só nomes de chaves e números de linha.

- **Entradas:** os dois arquivos-texto, que podem estar malformados.
- **Saídas:** uma linha por problema (`[ERRO] LLM_API_KEY: obrigatória e ausente`,
  `[AVISO] LST_HTTP_TIMEOUT: chave desconhecida (linha 17)`), um resumo e o código de saída:
  0 sem erros, 1 com erros, 2 arquivo inexistente.
- **Regras:** chave sem valor no modelo é obrigatória; chave desconhecida, nome legado e linha
  repetida geram avisos; linha fora do formato `CHAVE=valor` é registrada só pelo número, porque
  pode ser um segredo colado sem a chave.
- **Exemplos:** 2 normais, 7 de limite (chave vazia, minúsculas, aspas, duplicata, arquivo de 0
  bytes…) e 4 de erro — entre eles, um valor-sentinela em todas as chaves que jamais pode
  aparecer na saída.

## Como orientei a geração

Além das instruções fixas do agente, a tarefa trocou "código limpo" por critérios verificáveis:
nomes esperados e uma lista de nomes proibidos (`data`, `result`, `tmp`, `helper`, `util`…);
quatro responsabilidades separadas (ler o texto, comparar, montar as mensagens, linha de comando)
— "nenhuma função lê arquivo E decide E imprime"; comentários que explicam decisões, não o
código; erros em português, sem `None` como sinal de falha e sem `except Exception`; um único
leitor para os dois arquivos; toda entrada inesperada vira aviso, nunca *traceback*; valores de
teste `fake-`; só biblioteca padrão (proibido importar `dotenv`, presente apenas como dependência
indireta); e "tamanho não é critério".

## Leitura crítica e revisão

O agente escreveu os testes antes do código, entregou o módulo com 23 testes novos, todas as
verificações verdes e os 13 exemplos funcionando. Na minha leitura, dois pontos se destacaram:
a estrutura devolvida pelo leitor **guardava o valor de cada chave** (um `repr` imprimia o
segredo), embora o programa só precisasse saber se o valor estava vazio; e o leitor era **mais
rígido que a biblioteca que o projeto usa de verdade** para ler o `.env` — `CHAVE = valor`, com
espaços, virava erro falso, e aspas mal fechadas viravam "OK" falso. Descobri isso executando a
biblioteca, não lendo; o próprio agente tinha declarado uma suposição sobre ela que estava errada.

Um segundo agente, sem ver o relatório do primeiro nem as minhas notas, apontou 9 itens com
localização e justificativa (4 `[bloqueia]`, 3 `[melhora]`, 2 `[estilo]`): confirmou os dois
pontos acima com evidência executada, achou um "OK" falso que eu não tinha visto e apontou
testes presos a detalhes que não são regra. A ambiguidade era **minha** — a regra de formato
estava escrita ao pé da letra — e eu a esclareci na tarefa, com cinco exemplos novos, antes de
pedir qualquer ajuste.

**Aceitei** o leitor compatível com a biblioteca real, a exaustividade da função de mensagens, o
desacoplamento dos testes e a renomeação de uma função. **Aceitei na forma mais forte** parar de
guardar o valor (o revisor oferecia só escondê-lo do `repr`; preferi eliminá-lo, para que "valores
nunca saem do leitor" seja verdade por construção). **Adaptei** a inclusão de um `assert` num
teste existente, criando um teste novo para não abrir exceção à regra "nunca editar teste
existente". **Rejeitei** juntar os dados de teste dos dois arquivos num só lugar: reduziria
linhas sem melhorar a leitura.

## Antes e depois

O ajuste que mais importou cabe em três linhas — a estrutura de cada chave lida:

```python
# antes                              # depois
key: str                             key: str
value: str   # o segredo inteiro     is_empty: bool   # só o fato necessário
lines: tuple[int, ...]               lines: tuple[int, ...]
```

O leitor passou de um formato literal para o formato que o projeto realmente aceita, sem mudar
nenhuma mensagem de saída. O módulo **cresceu** (459 → 494 linhas) e ganhou uma função; a
evidência da melhoria está na tabela abaixo, não nesses números.

## Verificações

| O que verifiquei | Antes | Depois |
|---|---|---|
| Lint, formatação, tipos e testes do projeto, rodados por mim | verdes, 230 testes | verdes, 239 testes |
| Exemplos da especificação, pela linha de comando real | 13/13 | 18/18 |
| Concordância com o leitor real do projeto em 24 formas de escrever o `.env` | **16/24** | **24/24** |
| Um `repr` mostra o segredo? | sim | não |
| Cinco sabotagens propositais no código | — | cada uma derrubou exatamente os testes esperados |

**Decisão: aceitar.**

## Comentários

Ajudaram as orientações que davam algo verificável em vez de um adjetivo: a lista de nomes, os
quatro papéis (viraram três funções puras e um subcomando de cinco instruções), "comentários
explicam decisões" (a docstring resultante foi o texto mais útil na revisão — inclusive para
flagrá-la em contradição com o código), "tamanho não é critério" e o valor-sentinela, que deu ao
agente e a mim o mesmo teste de aceitação. Não ajudou a minha regra de formato ao pé da letra:
um agente obediente fez o que pedi, e o resultado contradizia o programa que a ferramenta existe
para prever. Regras "bem definidas" precisam ser definidas em relação ao sistema real, e só
executá-lo resolveu — nem a leitura, nem a suposição do agente, nem a minha memória. Sobre
"reduzir linhas não é melhoria": a versão final é maior e é melhor, porque a concordância foi de
16/24 para 24/24 e o segredo deixou de ficar guardado; a única sugestão rejeitada era a que só
reduzia linhas. A lição entrou nas instruções fixas do agente: suposição sobre biblioteca vizinha
se verifica executando, com o resultado no relatório.

## Reflexão: e na equipe?

O critério que eu incorporaria é o que decidiu este exercício: **nenhuma afirmação sobre como um
sistema vizinho se comporta entra no código sem ter sido executada**, e todo apontamento de
revisão diz onde está, por que importa e com que peso (`[bloqueia]`, `[melhora]`, `[estilo]`).
Nossas ferramentas de automação dependem o tempo todo de vizinhos que "todo mundo sabe como
funcionam" — a saída de um comando, o formato de um arquivo, a API de um serviço —, e é aí que
uma suposição plausível e errada produz um "OK" falso, mais caro que um erro visível. Na rotina,
mudaria pouco: cada tarefa dada a um agente nasce com uma página de especificação (entradas,
saídas, regras, exemplos normal/limite/erro) guardada junto com o código; as três classes viram
campo obrigatório do *pull request*, e um `[bloqueia]` sem evidência executada não bloqueia; quem
revisa não é quem gerou; e "pronto" inclui rodar os exemplos da especificação. Custa cerca de uma
hora por tarefa pequena — aqui, essa hora encontrou dois "OK" falsos que teriam ido para
produção com todas as verificações verdes e 100% de cobertura.
