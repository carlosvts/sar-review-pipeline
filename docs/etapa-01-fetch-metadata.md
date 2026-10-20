[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Etapa 01: `fetch_metadata`

1. Lê os DOIs de `data/start_set_dois.csv`.
2. Busca o start set no OpenAlex por DOI, em uma única chamada (filtro com DOIs separados por `|`).
3. Reconstrói cada abstract a partir do `abstract_inverted_index`.
4. Reúne os `referenced_works` do start set, descarta os já vistos e busca os metadados das referências em lotes de 50 IDs.
5. Salva tudo em disco.

## Arquivos gerados

| Arquivo | Conteúdo |
|---------|----------|
| `data/raw/start_set.json` | resposta bruta do start set |
| `data/raw/backward.json` | resposta bruta do backward, acumulada entre rodadas |
| `data/raw/unresolved_ids.txt` | IDs que o OpenAlex citou, mas para os quais não devolveu registro (acumulado) |
| `data/jsonl/start_set.jsonl` | um `Work` por linha |
| `data/jsonl/backward.jsonl` | um `Work` por linha |

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
| `backward_round` | 0 = start set, 1 = primeira rodada de backward, e assim por diante |
| `oa_locations` | URLs candidatas para texto completo (etapa 04); só locations com `is_oa` verdadeiro, `[]` se não houver (ver abaixo) |

Cada item de `oa_locations` tem o formato
`{"pdf_url", "landing_page_url", "source", "license", "version", "is_best"}`
(todos `str | null`, exceto `is_best: bool`). A `best_oa_location` do OpenAlex vem primeiro, com `is_best = true`; locations repetidas e itens sem `pdf_url` e sem `landing_page_url` são descartados.

`has_abstract` é uma propriedade calculada e não vai para o JSONL.
