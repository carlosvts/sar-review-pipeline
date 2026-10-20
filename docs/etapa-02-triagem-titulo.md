[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Etapa 02: triagem por título

Execute `uv run step02-screen-titles` depois da etapa 01. O script lê os works
de `data/jsonl/backward.jsonl`, que acumula as rodadas backward e guarda o
`backward_round` de cada work. Os registros são identificados pelo ID.

Os termos que definem o que deve ser mantido são declarados em
`EXCLUSION_RULES`, no arquivo `src/sar_review_pipeline/screening.py`.
Cada `TitleScreeningRule` tem um nome e uma tupla de palavras ou expressões.
A comparação é literal, sem diferença entre maiúsculas e minúsculas. Se o
título contiver qualquer termo de qualquer regra, o work passa pela triagem;
se não contiver nenhum, é excluído pelo título. A primeira regra/termo
correspondente fica registrada.

Por exemplo, `TitleScreeningRule(name="tema", keywords=("social robots",))`
mantém títulos contendo “social robots”. As regras funcionam como alternativas
(OR): corresponder a qualquer termo é suficiente. Sem regras configuradas, os
registros ficam `pending_rules`, sem serem mantidos ou excluídos
automaticamente; sem título, ficam `pending_title`.

Os resultados são `data/raw/title_screening.json` e
`data/jsonl/title_screening.jsonl`. O JSON bruto é um array de registros; o
JSONL contém um registro por linha. Ambos são acumulados por ID: em execuções
posteriores, novos works são adicionados sem apagar a triagem já registrada;
para IDs existentes, `backward_round` é sincronizado com o valor do work em
`data/jsonl/backward.jsonl`, e os demais campos de triagem são preservados.
`passed_title` indica que o work correspondeu a pelo menos um critério e pode
seguir para a próxima etapa — não significa inclusão final.
`excluded_by_title` indica que nenhum critério correspondeu. A regra e o termo
que justificaram a passagem ficam em `matched_rule` e `matched_keyword`.
