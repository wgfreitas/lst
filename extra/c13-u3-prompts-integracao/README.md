# Prompts para testes de integração com GenAI (C13, Unidade 3) — LST

| Arquivo | O que é |
|---|---|
| `resposta-prompts-integracao.md` | **A resposta do exercício**: cenário, tipos de prompt, casos gerados, comentários (1) e (2) |
| `anexo-prompts-e-casos.md` | Método, gabarito, contrato, prompts literais, registro de todos os casos gerados, mutantes e lacunas |
| `prompts/` | Contrato da integração, os cinco prompts e o teste-exemplo do few-shot |
| `saidas/` | Respostas literais do modelo (`claude-opus-5-5`), incluindo a interação de correção |
| `medidas/` | Resultados de mutação por suíte e o registro dos casos (JSON) |
| `ferramentas/` | Scripts usados na medição: gabarito, extração dos testes, mutação, análise e registro |

## Como reproduzir (opcional)

Na raiz do repositório, com o ambiente virtual do projeto ativo:

```bash
P=extra/c13-u3-prompts-integracao
python $P/ferramentas/gabarito.py .                                   # gabarito: 21 situações pela CLI real
python $P/ferramentas/extrair_blocos.py $P/saidas/p1-v1.md tests/test_gen_p1_v1.py
python -m pytest tests/test_gen_p1_v1.py --no-cov -q                  # 142 passam, 7 falham (D1, D2)
python $P/ferramentas/mutacao.py . tests/test_gen_p1_v1.py            # 18 de 18 mutantes mortos
rm tests/test_gen_p1_v1.py                                            # não deixe testes gerados em tests/
```

Os testes gerados ficam só dentro de `saidas/*.md`: vários falham de propósito (revelam os
defeitos D1–D3) e quebrariam o CI se fossem para `tests/`. O script de mutação altera o código em
`src/` e o restaura ao final de cada mutante; não o interrompa no meio.
