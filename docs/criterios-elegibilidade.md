[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Critérios de elegibilidade (protocolo, seção 5)

Aplicados na decisão do texto completo de cada rodada (`r<N>/fulltext/decisions.csv`). Toda exclusão registra o código do critério na coluna `reason`.

## Inclusão

- **IC1** Estudo envolvendo um robô social ou socialmente assistivo.
- **IC2** O estudo apresenta, avalia ou discute pelo menos uma característica de design da interação relacionada a uma das quatro questões de pesquisa.
- **IC3** A característica investigada está relacionada a pelo menos uma das seguintes dimensões: características físicas e visuais; modalidades e estratégias de comunicação; emoções, expressividade e personalidade; ou métodos de avaliação.
- **IC4** O estudo apresenta evidências provenientes de interação com participantes humanos ou uma análise sistemática de características de design fundamentada em interação humano–robô.
- **IC5** Texto completo disponível.
- **IC6** Publicação revisada por pares.

## Exclusão

- **EC1** Robô sem componente social ou assistivo relevante.
- **EC2** Estudo puramente técnico sem relação com o design da interação humano–robô.
- **EC3** Trabalho que não apresenta nenhuma característica relevante para responder às quatro questões de pesquisa.
- **EC4** Revisões, mapeamentos e outros estudos secundários. Estes poderão ser utilizados para identificar estudos adicionais, mas serão excluídos da síntese principal.
- **EC5** Resumo, pôster, editorial ou trabalho com conteúdo insuficiente para responder às questões de pesquisa.
- **EC6** Texto completo indisponível após tentativa de acesso.
- **EC7** Duplicata.
- **EC8** Trabalho já analisado em uma iteração anterior.

## Como a pipeline cobre cada critério

| Critério | Onde |
|---|---|
| EC6 | etapa 04: download automático (acesso aberto) e busca manual pela UFLA; o que nenhuma das duas recuperou sai com EC6 |
| EC7, EC8 | etapa 01: um work já visto (por ID do OpenAlex ou DOI) em qualquer rodada ou direção é ignorado |
| IC2, IC3, EC3 | etapa 05: os trechos do RAG por QP apoiam a leitura humana |
| IC1, IC4, IC6, EC1, EC2, EC4, EC5 | leitura humana do texto completo |
