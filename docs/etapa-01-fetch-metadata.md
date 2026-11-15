[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Etapa 01: `snowball`

A coleta é a única parte da pipeline que depende da direção. As duas usam o OpenAlex como formato e espaço de IDs comum (`snowball/openalex.py`), e cada rodada passa pela triagem por título da etapa 02 antes de definir a fronteira seguinte: só `passed_title` vira fronteira.

## Backward (`uv run step01-snowball`)

1. Lê os DOIs de `data/start_set_dois.csv`.
2. Busca o start set no OpenAlex por DOI, em uma única chamada (filtro com DOIs separados por `|`).
3. Reconstrói cada abstract a partir do `abstract_inverted_index`.
4. Reúne os `referenced_works` da fronteira, descarta os já vistos e busca os metadados das referências em lotes de 50 IDs.
5. Salva tudo em disco, triagem por título, nova fronteira; para quando uma rodada não traz nenhum `passed_title`.

`uv run step01-fetch` roda só o start set e a rodada 1, sem triagem; `uv run step02-screen-titles` faz só a triagem do que já foi baixado.

## Forward (`uv run step01-snowball forward`)

Roda depois do backward completo e da exclusão por cluster, sobre o que o backward incluiu.

1. Rodada 1: os seeds são o start set e os incluídos do backward (`data/jsonl/included.jsonl`). Rodada n: os works do forward da rodada anterior que passaram pelo título.
2. Para cada lote de 50 seeds:
   - **OpenAlex:** filtro `cites:W1|W2|...`, paginado por cursor.
   - **Semantic Scholar:** citações de cada seed com DOI. Os DOIs que ainda não foram vistos são buscados no OpenAlex pelo DOI, para que todo work tenha o mesmo formato e o mesmo ID. Citações sem DOI, ou com DOI que o OpenAlex não conhece, só entram na contagem do `forward_s2_log.jsonl`. `--no-s2` desliga essa fonte.
3. Works já vistos no start set, no backward ou no forward são descartados.
4. Triagem por título (`--direction forward`) e nova fronteira; para quando uma rodada não traz nenhum `passed_title`, ou no limite de `--max-rounds N` (protocolo, 4.4).

Opções: `--max-rounds N` (limite de rodadas) e `--no-s2` (só o OpenAlex).

As chaves ficam no `.env` (modelo e explicação de cada variável em `.env.example`): `OPENALEX_API_KEY` para o OpenAlex e, opcional, `S2_API_KEY` para o Semantic Scholar, que sem ela usa a cota compartilhada e uma pausa maior entre chamadas.

Os arquivos do forward só crescem (append): a coleta pode ser interrompida e retomada. Cada fonte registra separadamente os seeds que concluiu (`forward_done_seeds.txt` para o OpenAlex, uma linha no `forward_s2_log.jsonl` para o Semantic Scholar), e o que já foi gravado não é buscado de novo. Uma falha do Semantic Scholar num seed (429 persistente, por exemplo) não para a coleta: o seed fica sem linha no log, a coleta espera 60 s e segue, e no fim avisa para rodar o mesmo comando de novo, que tenta só os seeds que faltaram. Para manter o raw num tamanho razoável, o forward pede ao OpenAlex só os campos que `Work.from_openalex` usa, mais `cited_by_count` (`SELECT` em `forward.py`).

## Arquivos gerados

| Arquivo | Conteúdo |
|---------|----------|
| `data/raw/start_set.json` | resposta bruta do start set |
| `data/raw/backward.json` | resposta bruta do backward, acumulada entre rodadas |
| `data/raw/unresolved_ids.txt` | IDs que o OpenAlex citou, mas para os quais não devolveu registro (acumulado) |
| `data/raw/forward_raw.jsonl` | resposta bruta do forward, um work por linha (campos de `SELECT`) |
| `data/raw/forward_done_seeds.txt` | seeds cujas citações já foram buscadas no OpenAlex |
| `data/raw/forward_s2_log.jsonl` | por seed concluído no Semantic Scholar: citações no Semantic Scholar, sem DOI, DOIs novos e quantos o OpenAlex resolveu |
| `data/jsonl/start_set.jsonl` | um `Work` por linha |
| `data/jsonl/backward.jsonl` | um `Work` por linha |
| `data/jsonl/forward.jsonl` | um `Work` por linha |

As etapas seguintes do forward gravam ao lado das do backward, com o prefixo `forward_` (`forward_title_screening.jsonl`, `forward_candidates.jsonl`, `forward_candidates_abstracts.jsonl`, `forward_included.jsonl`) e em `data/cluster/forward/`. A lista completa está em `direction.py`.

## Campos de `Work`

| Campo | Descrição |
|-------|-----------|
| `id` | ID do OpenAlex (URL completa) |
| `doi` | DOI em minúsculas, sem o prefixo `https://doi.org/` |
| `title` | título |
| `abstract` | abstract reconstruído, ou `null` |
| `abstract_source` | de onde veio o abstract: `"openalex"` ou `null` na etapa 01; a etapa 03 acrescenta as outras fontes |
| `authors` | lista de nomes dos autores |
| `publication_year` | ano de publicação |
| `type` | tipo do trabalho segundo o OpenAlex |
| `language` | idioma |
| `is_retracted` | se o trabalho foi retratado |
| `is_paratext` | se é paratexto (capa, sumário etc.) |
| `referenced_works` | IDs do OpenAlex das referências |
| `backward_round` | rodada em que o work entrou, na direção de `direction`: 0 = start set, 1 = primeira rodada, e assim por diante (o nome é de antes do forward) |
| `oa_locations` | URLs candidatas para texto completo (etapa 04); só locations com `is_oa` verdadeiro, `[]` se não houver (ver abaixo) |
| `direction` | `"start_set"`, `"backward"` ou `"forward"`; JSONL anteriores ao forward, sem o campo, leem `"backward"` |

Cada item de `oa_locations` tem o formato
`{"pdf_url", "landing_page_url", "source", "license", "version", "is_best"}`
(todos `str | null`, exceto `is_best: bool`). A `best_oa_location` do OpenAlex vem primeiro, com `is_best = true`; locations repetidas e itens sem `pdf_url` e sem `landing_page_url` são descartados.

`has_abstract` é uma propriedade calculada e não vai para o JSONL.
