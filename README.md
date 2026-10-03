# sar-review-pipeline

Pipeline em Python para automatizar uma revisão sistemática com snowballing sobre robôs socialmente assistivos (SARs), desenvolvida na UFLA.

O snowballing backward manual gerou artigos demais para triar à mão. O pipeline automatiza a coleta e a triagem, mantendo um humano na decisão final. Os scripts são escritos à mão pelo autor, por fazerem parte do processo científico.

## Etapas

| # | Etapa | Estado |
|---|-------|--------|
| 01 | Buscar no OpenAlex os metadados do start set e das referências (backward) | implementada |
| 02 | Cortar por título, registrando a regra que cortou cada artigo | planejada |
| 03 | Triar os sobreviventes pelo abstract, buscando em outra fonte quando o OpenAlex não o trouxer | planejada |
| 04 | Baixar o texto completo dos incluídos | planejada |
| 05 | RAG: recuperar, em cada artigo, o trecho que mais provavelmente responde a cada pergunta de pesquisa | planejada |
| 06 | Supervisão humana: sim ou não para cada resposta | planejada |
| 07 | Tabela final redigida por LLM e análise estatística em pandas | planejada |

Cada etapa é um subpacote de `sar_review_pipeline`. Nomes de pacote Python não podem começar com número, então a etapa 01 se chama `fetch_metadata`, e não `01_fetch_metadata`. A ordem fica registrada nesta tabela e no nome do comando (`step01-fetch`).

## Como rodar

Requer [uv](https://docs.astral.sh/uv/) e Python 3.12 ou superior.

```bash
uv sync
uv run step01-fetch
# equivalente:
uv run python -m sar_review_pipeline.fetch_metadata
```

Rode sempre da raiz do projeto: os caminhos `data/...` são relativos ao diretório atual.

## Estrutura

```
data/
  start_set_dois.csv      entrada: coluna `doi`, 16 DOIs do start set
  raw/                    saída: respostas brutas da API (fora do git)
  jsonl/                  saída: formato de trabalho (fora do git)
src/sar_review_pipeline/
  work.py                 dataclass Work, normalize_doi, rebuild_abstract
  fetch_metadata/
    parser.py             DoiParser: lê os DOIs do CSV
    api.py                OpenAlexSnowballer: busca, acumula e salva
    __main__.py           ponto de entrada da etapa 01
```

## Etapa 01: `fetch_metadata`

1. Lê os DOIs de `data/start_set_dois.csv`.
2. Busca o start set no OpenAlex por DOI, em uma única chamada (filtro com DOIs separados por `|`).
3. Reconstrói cada abstract a partir do `abstract_inverted_index`.
4. Reúne os `referenced_works` do start set, descarta os já vistos e busca os metadados das referências em lotes de 50 IDs.
5. Salva tudo em disco.

### Arquivos gerados

| Arquivo | Conteúdo |
|---------|----------|
| `data/raw/start_set.json` | resposta bruta do start set |
| `data/raw/backward.json` | resposta bruta do backward, acumulada entre rodadas |
| `data/raw/unresolved_ids.txt` | IDs que o OpenAlex citou, mas para os quais não devolveu registro (acumulado) |
| `data/jsonl/start_set.jsonl` | um `Work` por linha |
| `data/jsonl/backward.jsonl` | um `Work` por linha |

### Campos de `Work`

| Campo | Descrição |
|-------|-----------|
| `id` | ID do OpenAlex (URL completa) |
| `doi` | DOI em minúsculas, sem o prefixo `https://doi.org/` |
| `title` | título |
| `abstract` | abstract reconstruído, ou `null` |
| `abstract_source` | de onde veio o abstract: hoje `"openalex"` ou `null` |
| `authors` | lista de nomes dos autores |
| `publication_year` | ano de publicação |
| `type` | tipo do trabalho segundo o OpenAlex |
| `language` | idioma |
| `is_retracted` | se o trabalho foi retratado |
| `is_paratext` | se é paratexto (capa, sumário etc.) |
| `referenced_works` | IDs do OpenAlex das referências |
| `backward_round` | 0 = start set, 1 = primeira rodada de backward, e assim por diante |

`has_abstract` é uma propriedade calculada e não vai para o JSONL.

## Decisões de projeto

- **JSON bruto e JSONL têm papéis diferentes.** O JSON bruto é cache e prova do que a API devolveu. O JSONL traz só os campos úteis ao filtro da etapa 02 e é o formato de trabalho das etapas seguintes.
- **Abstract ausente nunca significa exclusão.** O artigo fica pendente de busca em outra fonte ou vai para a fila manual. Alguns itens, como matérias de divulgação, não têm abstract em nenhuma fonte.
- **`abstract_source` registra a origem de cada abstract**, para que as fontes adicionadas na etapa 03 fiquem rastreáveis.
- **O start set é rebuscado a cada execução; o backward é acumulado.** `load_backward()` carrega do disco as rodadas anteriores, e só os IDs ainda não vistos são buscados.
- **`save()` reescreve os arquivos inteiros.** Por isso, `load_backward()` precisa ser chamado antes de `fetch_backward()` e `save()`: sem ele, o que foi acumulado nas rodadas anteriores é sobrescrito.
