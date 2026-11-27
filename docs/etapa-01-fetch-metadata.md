[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Etapa 01: `snowball`

O snowballing segue o método do Wohlin: em cada rodada, os artigos selecionados na rodada anterior passam por backward e forward ao mesmo tempo, os works novos passam pela triagem completa (título, abstract e cluster, texto completo) e só os selecionados no texto completo viram os seeds da rodada seguinte. Um work já visto em qualquer rodada anterior é ignorado. O snowballing para quando uma rodada não seleciona nenhum artigo novo.

Tudo fica em `data/rounds/` (caminhos em `rounds.py`). O OpenAlex é o formato e o espaço de IDs comum (`snowball/openalex.py`).

## Rodada 0: start set (`uv run step01-snowball start`)

Lê os DOIs de `data/start_set_dois.csv` e busca o start set no OpenAlex numa única chamada. O start set entra como selecionado, sem triagem, e é o seed da rodada 1. É buscado só uma vez; `--force` busca de novo.

## Rodada N (`uv run step01-snowball round N`)

Os seeds são `r<N-1>/selected.jsonl` (na rodada 1, o start set). Para cada lote de 50 seeds:

- **Backward:** os `referenced_works` dos seeds, buscados no OpenAlex em lotes de 50 IDs. O que o OpenAlex cita mas não devolve vai para `unresolved_ids.txt`.
- **Forward, OpenAlex:** filtro `cites:W1|W2|...`, paginado por cursor.
- **Forward, Semantic Scholar:** citações de cada seed com DOI. Os DOIs novos são buscados no OpenAlex pelo DOI, para que todo work tenha o mesmo formato e o mesmo ID. Citações sem DOI, ou com DOI que o OpenAlex não conhece, só entram na contagem do `forward_s2_log.jsonl`. `--no-s2` desliga essa fonte.

Um work que aparece pelas duas direções na mesma rodada entra uma vez, com `direction = "both"`. Cada aresta seed → work fica em `hits.jsonl`, que diz por qual seed e direção cada artigo chegou. No fim, o comando roda a triagem por título da etapa 02 sobre os works da rodada.

As chaves ficam no `.env` (modelo e explicação de cada variável em `.env.example`): `OPENALEX_API_KEY` para o OpenAlex e, opcional, `S2_API_KEY` para o Semantic Scholar, que sem ela usa a cota compartilhada e uma pausa maior entre chamadas.

A coleta pode ser interrompida e retomada: `works.jsonl`, `raw.jsonl` e `hits.jsonl` só crescem (append), e cada fonte registra os seeds que concluiu (`backward_done_seeds.txt`, `forward_done_seeds.txt` e uma linha por seed no `forward_s2_log.jsonl`). Uma falha do Semantic Scholar num seed (429 persistente, por exemplo) não para a coleta: o seed fica sem linha no log, a coleta espera 60 s e segue, e no fim avisa para rodar o mesmo comando de novo, que tenta só os seeds que faltaram. No fim da coleta, `works.jsonl` é reescrito com a direção de cada work. O OpenAlex devolve só os campos que `Work.from_openalex` usa, mais `cited_by_count` (`SELECT` em `collect.py`).

## Arquivos gerados (`data/rounds/r<N>/`)

| Arquivo | Conteúdo |
|---------|----------|
| `raw.jsonl` | resposta bruta do OpenAlex, um work por linha (campos de `SELECT`) |
| `works.jsonl` | um `Work` por linha |
| `hits.jsonl` | `{seed, work, direction}`: cada aresta do grafo de citações que trouxe um work da rodada |
| `unresolved_ids.txt` | IDs citados pelos seeds para os quais o OpenAlex não devolveu registro |
| `backward_done_seeds.txt` | seeds com as referências já buscadas |
| `forward_done_seeds.txt` | seeds com as citações do OpenAlex já buscadas |
| `forward_s2_log.jsonl` | por seed concluído no Semantic Scholar: citações, sem DOI, já na rodada, DOIs novos e quantos o OpenAlex resolveu |

Na rodada 0 ficam só `raw.jsonl` e `works.jsonl` (o start set).

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
| `round` | rodada do snowballing em que o work entrou: 0 = start set, 1 = primeira rodada, e assim por diante |
| `oa_locations` | URLs candidatas para texto completo (etapa 04); só locations com `is_oa` verdadeiro, `[]` se não houver (ver abaixo) |
| `direction` | por onde o work entrou na rodada: `"start_set"`, `"backward"`, `"forward"` ou `"both"` (achado pelas duas direções) |

Cada item de `oa_locations` tem o formato
`{"pdf_url", "landing_page_url", "source", "license", "version", "is_best"}`
(todos `str | null`, exceto `is_best: bool`). A `best_oa_location` do OpenAlex vem primeiro, com `is_best = true`; locations repetidas e itens sem `pdf_url` e sem `landing_page_url` são descartados.

`has_abstract` é uma propriedade calculada e não vai para o JSONL.
