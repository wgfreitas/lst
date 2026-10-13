# Prompts para testes de integração com GenAI — LST

## O cenário de integração

O LST (Log Sec Triage) é uma CLI que lê um log, detecta eventos suspeitos e pede a um LLM, por uma
API REST compatível com OpenAI (`POST /chat/completions`), uma explicação de cada evento. É a
fronteira onde mais componentes conversam: a configuração vira uma requisição HTTP, a resposta é
interpretada e entra no relatório, e os erros viram mensagens e códigos de saída na CLI. Nos
testes, todos os componentes são reais; só o servidor é simulado (com respx), sem rede.

Para dar ao modelo a especificação do cenário — o papel do OpenAPI nos exemplos da unidade —,
escrevi um **contrato de uma página** só a partir da documentação do projeto, sem olhar o código:
pontos de entrada, faixas de configuração, formato da requisição, respostas esperadas, códigos de
saída e mensagens.

## Os tipos de prompt

| | Finalidade | Técnica da unidade | Estrutura |
|---|---|---|---|
| **P1** | Cenários de integração e dados de teste | Zero-shot estruturado, caixa-preta (Fig. 16 e 28) | Papel + critério (Particionamento de Equivalência e Valor-Limite) + contrato + formato |
| **P2** | Casos de erro na comunicação | Cadeia de raciocínio + few-shot (Fig. 10 e 11) | Passos: pontos de comunicação → falhas → comportamento esperado → bordas → um teste por falha, seguindo um teste-exemplo |
| P0 | Linha de base: o mesmo pedido, sem contrato | Zero-shot puro (Fig. 9) | Um parágrafo |

## Como experimentei

Cada prompt rodou numa sessão nova do Opus 5.5 (`claude-opus-5-5`), sem histórico e sem acesso
ao código, como numa chamada de API, e os testes gerados foram executados contra o código real.
Antes, medi o comportamento do LST em 21 situações; esse gabarito separa "o teste está errado" de
"o LST está errado". Medi a qualidade como a unidade propõe — execução, cobertura e mutação, com 18
mutantes que simulam falhas de integração — e acrescentei os defeitos reais encontrados.

## O que foi gerado

| Execução | Casos | Passam | Defeitos revelados | Mutantes mortos | Casos que bastam* |
|---|---|---|---|---|---|
| P0 — zero-shot puro | 21 | 0 | — | — | — |
| P1 v1 — cenários | 149 | 142 (95%) | D1, D2 | 18/18 | 14 |
| P2 v1 — erros | 77 | 74 (96%) | D2 | 16/18 | 11 |
| P1 v2 — cenários ajustado | 52 | 39 (75%) | D1, D3 | 16/18 | 13 |
| P2 v2 — erros ajustado | 48 | 33 (69%) | D1, D2, D3 | 17/18 | 15 |
| Suíte do próprio projeto | 239 | 239 | nenhum | 10/18 | — |

\* Menor subconjunto que mata os mesmos mutantes e revela os mesmos defeitos.

Os testes encontraram **três defeitos reais**:

- **D1** — `LLM_TIMEOUT_SECONDS` é aceito, mas nunca aplicado: toda chamada usa 60 s.
- **D2** — uma resposta 200 fora do formato esperado (sem `choices`, corpo vazio, HTML de uma URL
  errada) derruba a triagem inteira com mensagens como "list index out of range", em vez de ir para
  "Eventos não explicados", como a documentação promete.
- **D3** — configuração fora da faixa (por exemplo, `LLM_TIMEOUT_SECONDS=999`) é reportada como
  "LLM_API_KEY não configurada".

Os três já estavam no gabarito; os modelos não o viram e chegaram a eles só pelo contrato. A suíte
do projeto, com a mesma cobertura (~98%) do módulo de integração, não acusa nenhum. Exemplos de
casos gerados (o registro completo está no anexo): "`LLM_TIMEOUT_SECONDS` nos limites 1,0 e 300,0
é aplicado em cada chamada" (P1, revelou o D1); "um 401 no segundo evento encerra a varredura e o
terceiro não é consultado" (P2, passou); "configuração inválida sai com código 1 e uma mensagem que
nomeia a variável" (P1 v2, revelou o D3).

## (1) Como cada tipo de prompt influenciou a qualidade e a diversidade

**Sem contrato, nada executa.** No P0, o modelo inventou a interface (uma função `main` e
variáveis `LST_API_KEY` que não existem), e os 21 casos falharam. Trouxe boas ideias — "linhas
benignas não devem sair para o provedor" —, mas nenhum teste útil.

**O prompt de cenários (P1) deu amplitude.** Partição e valor-limite sobre o contrato cobriram as
duas frentes da integração: o que o LST envia (cada configuração conferida dentro da requisição) e
como ele reage a cada classe de resposta. Foi a pergunta "o timeout configurado chega à
requisição?" que encontrou o D1. O preço foi o volume: 149 casos, quando 14 bastavam — oito
severidades e catorze conteúdos inválidos são variações da mesma classe.

**O prompt de erros (P2) deu profundidade.** O raciocínio passo a passo trouxe casos que o P1 não
teve — 401 no meio do lote, conexão recusada ou derrubada, os dois contadores de novas tentativas
independentes — e expôs onde o contrato era omisso ("timeout tem nova tentativa?"), sem inventar a
resposta. Mas, focado em
falhas, quase não conferiu se a configuração chega à requisição: perdeu o D1 e os mutantes do
modelo e das amostras.

**Com contrato, nenhum oráculo foi inventado.** Toda falha apontou um defeito real ou o requisito
de mensagens descrito adiante. Por isso a taxa de sucesso caiu de ~95% para ~70% da v1 para a v2:
os testes ficaram mais exigentes e acharam mais. Contra um sistema real, que tem defeitos, a taxa
de sucesso não mede a qualidade dos testes. A cobertura também não mediu: ficou em ~97–98% em
todas as suítes com contrato e na do projeto, enquanto a mutação variou de 10 (projeto) a 18
mutantes mortos.

## (2) Quais ajustes de prompt foram necessários

**Dar contexto executável (P0 → v1).** O contrato com pontos de entrada, faixas, formato da
requisição, códigos de saída e o dado "a fixture gera exatamente 3 eventos" levou de 0% a ~95% de
testes aprovados, todos executáveis, sem nenhum erro de import ou de montagem. Foi o ajuste de
maior efeito.

**Pedir "corrija os testes que falharam" não bastou** (a primeira alternativa da unidade,
Figura 30). Diferente do que a unidade relata, o modelo não afrouxou os oráculos: reconheceu o D2
como defeito do LST. Mas errou parte do diagnóstico do timeout e decidiu sozinho marcar defeitos
abertos como "falha esperada" — o que deixaria o CI verde com os defeitos lá. Essa decisão é do
responsável, não do modelo.

**Alterar o prompt com o que as execuções ensinaram (v1 → v2)**, a terceira alternativa:

1. **"Valor aceito não é valor aplicado"**: o P2 v2 passou a encontrar o D1 e subiu para 17
   mutantes mortos.
2. **Requisito de qualidade da equipe — a mensagem de erro nomeia a causa** e não expõe exceção
   interna. O contrato era omisso; sem esse critério, não havia oráculo. Os dois tipos encontraram o
   D3 e mensagens de timeout e de conexão que não dizem o que corrigir.
3. **Lacunas viram perguntas, não asserções**: foram 23 e 19 perguntas ao responsável, várias
   exatamente sobre os defeitos. Efeito colateral: o P1 v2 transformou o D2 em pergunta e deixou de
   testá-lo.
4. **Um caso por classe, parametrização só nos limites**: de 149 para 52 casos e de 77 para 48.

**Dois ajustes que a v2 ainda pede.** *Uma regra por teste*: testes que juntavam código de saída,
mensagem e requisito da equipe já nasceram vermelhos e ficaram cegos para regressões no mesmo
caminho (o mutante "timeout sai com código 2" sobreviveu às duas v2). E *informar no prompt o que a
execução revelou sobre a biblioteca*: o P2 v2 supôs que `Retry-After: 0` dispensa a espera entre
tentativas; o SDK ignora esse valor, e um único teste levou 14 s.

## Em resumo

O tipo de prompt decide onde o modelo procura: o P1 na amplitude do contrato, o P2 na profundidade
das falhas. O contexto decide se o que ele gera executa. E o valor dos testes só apareceu porque
eles foram executados contra o sistema real e comparados com um gabarito: pela taxa de sucesso, a
melhor versão seria a que encontrou menos defeitos.

**Limitações:** uma execução por prompt; um modelo forte (modelos menores tendem a errar mais
oráculos); um contrato escrito por quem conhece o projeto; 18 mutantes feitos à mão.
