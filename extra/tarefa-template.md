# TAREFA — <título curto, imperativo>

<!-- Parte VARIÁVEL do agente desenvolvedor: preencher a cada uso. A parte
     fixa (papel, regras, contexto, protocolo de lacunas, formato) é o
     CLAUDE.md da raiz. Campo difícil de preencher = decisão ainda não
     tomada — resolva antes de gerar, não durante. -->

**Tipo:** implementar | testar | corrigir | explicar
**Tamanho-alvo:** 1 comportamento · ≤ N arquivos de produção · cabe em 1 sessão

## Contexto da tarefa

- Para que existe / quem chama / de onde vem a entrada:
- Módulo(s)-alvo e testes espelhados:
- Código vizinho a imitar (arquivo:função):
- Decisões já tomadas que se aplicam (CHANGELOG, commit, doc, ADR):

## Contrato

- Assinatura exata (nome, parâmetros, tipos, retorno):
- Erros (qual entrada levanta qual exceção, com que mensagem):
- Comportamentos que importam, em ordem de importância:
  1.
  2.
  3.

## Exemplos que definem o contrato

- `<entrada>` → `<saída exata>`
- `<entrada inválida>` → `<erro esperado>`

## Se tipo = corrigir — reprodução obrigatória

- Comportamento esperado:
- Comportamento observado:
- Reprodução mínima (menor entrada que dispara o problema):
- Traceback literal (sem cortes):

## Se tipo = explicar — leitura, não alteração

- Código sob leitura (arquivo:linhas):
- O que se sabe de fato (quem chama, desde quando):
- Motivo do interesse (a mudança que se pretende fazer depois):

## Fora de escopo desta tarefa

-

## Critérios de aceitação (verificáveis)

- [ ] Testes: <nomes ou comportamentos que devem existir e passar>
- [ ] Os 4 checks verdes na suíte completa; contagem de testes N → M
- [ ] Contratos públicos intocados (ou gate autorizado abaixo)
- [ ] Docs: <quais atualizar, ou "nenhum">

## Gates pré-autorizados nesta tarefa

- (nenhum) | `aprovado: <gate exato, ex.: "tocar README EN+PT, seção Limitations">`
