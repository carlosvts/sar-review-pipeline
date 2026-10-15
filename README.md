# sar-review-pipeline

Pipeline em Python para automatizar uma revisão sistemática com snowballing sobre robôs socialmente assistivos (SARs), desenvolvida na UFLA.

O snowballing backward manual gerou artigos demais para triar à mão. O pipeline automatiza a coleta e a triagem, mantendo um humano na decisão final. Os scripts são escritos à mão pelo autor, por fazerem parte do processo científico.

## Etapas

| # | Etapa | Estado |
|---|-------|--------|
| 01 | Buscar no OpenAlex os metadados do start set e das referências (backward) | implementada |
| 02 | Cortar por título, registrando a regra que cortou cada artigo | implementada; regras pendentes (Patricia)|
| 03 | Triar os sobreviventes pelo abstract, buscando em outra fonte quando o OpenAlex não o trouxer | planejada (Patricia)|
| 04 | Baixar o texto completo dos incluídos | planejada (Carlos)|
| 02 | Cortar por título, registrando a regra que cortou cada artigo | pendente (Patricia)|
| 03 | Triar os sobreviventes pelo abstract, buscando em outra fonte quando o OpenAlex não o trouxer | (Patricia)|
| 04 | Baixar o texto completo dos incluídos e extrair o texto em parágrafos | implementada (Carlos)|
| 05 | RAG: recuperar, em cada artigo, o trecho que mais provavelmente responde a cada pergunta de pesquisa | planejada (Carlos)|
| 06 | Supervisão humana: sim ou não para cada resposta | planejada (Ambos)|
| 07 | Tabela final redigida por LLM e análise estatística em pandas | planejada (Ambos)|

Cada etapa é um subpacote de `sar_review_pipeline`. Nomes de pacote Python não podem começar com número, então a etapa 01 se chama `fetch_metadata`, e não `01_fetch_metadata`. A ordem fica registrada nesta tabela e no nome do comando (`step01-fetch`, `step04-fulltext`).

Como a etapa 02 ainda está pendente, a etapa 04 roda hoje sobre uma amostra do backward, e não sobre a lista final de incluídos (ver [Etapa 04](#etapa-04-fulltext)).

## Como rodar

Requer [uv](https://docs.astral.sh/uv/) e Python 3.12 ou superior.

```bash
uv sync

# etapa 01: metadados do start set e do backward
uv run step01-fetch
uv run step02-screen-titles
# equivalente:
uv run python -m sar_review_pipeline.fetch_metadata

# etapa 04: baixa o texto completo (amostra do backward)
uv run step04-fulltext
# etapa 04: extrai o texto do que já foi baixado
uv run step04-fulltext extract
# extrai de novo, mesmo o que já foi extraído
uv run step04-fulltext extract --force
```

Rode sempre da raiz do projeto: os caminhos `data/...` são relativos ao diretório atual.

A variável de ambiente `S2_API_KEY` é opcional: se existir, é enviada ao Semantic Scholar para aumentar o limite de requisições.

## Estrutura

```
data/
  start_set_dois.csv      entrada: coluna `doi`, 16 DOIs do start set
  raw/                    saída da etapa 01: respostas brutas da API
  jsonl/                  saída da etapa 01: formato de trabalho
  fulltext/               saída da etapa 04
    manifest.csv          uma linha por work, com o estado do download
    manual_queue.csv      works que nenhuma fonte resolveu
    manual_queue.ris      os mesmos works, para importar no Zotero
    docs/                 PDFs e XMLs baixados (W….pdf, W….xml)
    text/                 texto extraído, um JSONL por documento (W….jsonl)
src/sar_review_pipeline/
  work.py                 dataclass Work, normalize_doi, rebuild_abstract, extract_oa_locations
  fetch_metadata/
    parser.py             DoiParser: lê os DOIs do CSV
    api.py                OpenAlexSnowballer: busca, acumula e salva
    __main__.py           ponto de entrada da etapa 01
  fulltext/
    manifest.py           Manifest: gera e atualiza o manifest.csv
    validate.py           Validator: diz se um arquivo baixado é utilizável
    download.py           Downloader: cascata de fontes e fila manual
    extract.py            Extractor: PDF/XML em parágrafos com seção e página
    __main__.py           ponto de entrada da etapa 04
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
| `oa_locations` | URLs candidatas para texto completo (etapa 04); só locations com `is_oa` verdadeiro, `[]` se não houver (ver abaixo) |

Cada item de `oa_locations` tem o formato
`{"pdf_url", "landing_page_url", "source", "license", "version", "is_best"}`
(todos `str | null`, exceto `is_best: bool`). A `best_oa_location` do OpenAlex vem primeiro, com `is_best = true`; locations repetidas e itens sem `pdf_url` e sem `landing_page_url` são descartados.

`has_abstract` é uma propriedade calculada e não vai para o JSONL.

## Etapa 02: triagem por título

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
## Etapa 04: `fulltext`

A etapa tem dois comandos: o download (`uv run step04-fulltext`) e a extração (`uv run step04-fulltext extract`).

### Download

1. Gera ou completa o `manifest.csv` com os works de `start_set.jsonl` e `backward.jsonl`. Se um ID aparece nos dois, fica o de menor `backward_round`.
2. Sorteia uma amostra reprodutível do backward (`SAMPLE_SIZE = 50`, `SEED = 42`, em `fulltext/__main__.py`).
3. Para cada work, percorre a cascata de fontes e fica com o primeiro arquivo que baixar e validar.
4. Imprime um resumo: quantos têm texto, por fonte, por tipo, e o motivo de cada falha.
5. Grava o resultado de cada work no manifesto.
6. Exporta a fila manual com o que nenhuma fonte resolveu.

### Cascata de fontes

A ordem está em `Downloader.SOURCES`. As candidatas saem de um gerador, então uma API só é consultada se as candidatas das fontes anteriores falharem.

| # | Fonte | De onde vem a URL |
|---|-------|-------------------|
| 1 | `openalex` | `pdf_url` de cada item de `oa_locations` |
| 2 | `pmc` | PMCID achado nas landing pages ou pela busca do DOI na Europe PMC; tenta o XML da Europe PMC, depois o XML do efetch do NCBI e por último o PDF renderizado da Europe PMC |
| 3 | `crossref` | links de texto completo que a editora depositou no metadado do DOI (só `text-mining` ou sem finalidade declarada; `api.elsevier.com` e `api.wiley.com` ficam de fora por exigirem token) |
| 4 | `landing_meta` | meta tags `citation_pdf_url`, `bepress_citation_pdf_url` e `eprints.document_url` das landing pages (no máximo 3 por work) |
| 5 | `semantic_scholar` | `openAccessPdf` e, se houver, o ID do arXiv em `externalIds` |
| 6 | `arxiv_title` | busca do título na API do arXiv; só aceita com similaridade de título ≥ 0,9 e, se o work tem autores, com algum sobrenome em comum |

Requisições usam retry com backoff para 429, 5xx, timeout e erro de conexão (respeitando `Retry-After`), pausa de 1 s entre works e de 3 s entre chamadas ao arXiv.

### Validação

O `Validator` identifica o tipo pelos primeiros bytes do arquivo, sem confiar na extensão nem no `Content-Type`.

- **PDF:** começa com `%PDF-`, tem pelo menos 10 KB e traz `%%EOF` no final.
- **XML (JATS):** bem formado, com um `<article>` na raiz ou dentro de `<pmc-articleset>`, e um `<body>` com pelo menos 2.000 caracteres.
- **HTML** é rejeitado com o motivo "paywall ou bloqueio?".

### Extração

O `Extractor` converte cada arquivo de `data/fulltext/docs/` em parágrafos e grava um JSONL por documento em `data/fulltext/text/`. Essa saída é a entrada do RAG da etapa 05.

- **XML:** segue a marcação do JATS. O abstract entra com a seção `Abstract`; o corpo é percorrido por `<sec>`, incluindo legendas de figuras e tabelas e itens de lista. Notas de rodapé, fórmulas e tabelas embutidas são removidas do texto.
- **PDF (PyMuPDF):** trabalha linha a linha, na ordem de leitura, tratando páginas de duas colunas. Cabeçalhos, rodapés e números de página são removidos, tanto pela margem quanto por se repetirem em várias páginas. Um título de seção precisa ter cara de título (negrito, fonte maior, caixa alta ou fonte própria) e forma de título (numerado, nome conhecido de seção ou linha sozinha). Blocos que são quase só números, como tabelas, são descartados.
- Nos dois formatos, a extração para na bibliografia e pula agradecimentos, financiamento, conflito de interesses, contribuições dos autores, disponibilidade de dados e declaração de ética.
- Documentos com pouco texto (menos de 10 parágrafos ou de 8.000 caracteres), sem texto ou sem nenhuma seção identificada são sinalizados no resumo para conferência manual.

### Arquivos gerados

| Arquivo | Conteúdo |
|---------|----------|
| `data/fulltext/manifest.csv` | uma linha por work, com o estado do download |
| `data/fulltext/docs/W….pdf` ou `W….xml` | texto completo baixado, nomeado pelo ID do OpenAlex |
| `data/fulltext/text/W….jsonl` | um parágrafo por linha |
| `data/fulltext/manual_queue.csv` | works sem texto, com links e motivo da falha; sobrescrito a cada execução |
| `data/fulltext/manual_queue.ris` | os mesmos works, para importar no Zotero e rodar "Find Available PDF" com o acesso institucional (rede ou VPN da UFLA) |

### Colunas de `manifest.csv`

| Coluna | Descrição |
|--------|-----------|
| `id`, `doi`, `title`, `publication_year`, `backward_round` | copiados do `Work` |
| `n_pdf_candidates` | quantas `oa_locations` têm `pdf_url` |
| `n_landing_only` | quantas `oa_locations` têm só `landing_page_url` |
| `status` | `pending`, `downloaded`, `failed` ou `manual` |
| `source_used` | fonte da cascata que resolveu o work |
| `url_used` | URL de onde o arquivo foi baixado |
| `kind` | `pdf` ou `xml` |
| `local_path` | caminho do arquivo em `data/fulltext/docs/` |
| `note` | motivo da falha, quando `status = failed` |

### Campos de `text/W….jsonl`

| Campo | Descrição |
|-------|-----------|
| `id` | ID do OpenAlex (URL completa) |
| `key` | ID curto, igual ao nome do arquivo (`W123`) |
| `kind` | `pdf` ou `xml` |
| `para` | índice do parágrafo no documento, a partir de 0 |
| `section` | caminho da seção (`2 Methods > 2.1 Participants`), ou `""` se não identificada |
| `page` | página no PDF, a partir de 1; `null` para XML |
| `text` | texto do parágrafo |

## Decisões de projeto

- **JSON bruto e JSONL têm papéis diferentes.** O JSON bruto é cache e prova do que a API devolveu. O JSONL traz só os campos úteis ao filtro da etapa 02 e é o formato de trabalho das etapas seguintes.
- **Abstract ausente nunca significa exclusão.** O artigo fica pendente de busca em outra fonte ou vai para a fila manual. Alguns itens, como matérias de divulgação, não têm abstract em nenhuma fonte.
- **`abstract_source` registra a origem de cada abstract**, para que as fontes adicionadas na etapa 03 fiquem rastreáveis.
- **O start set é rebuscado a cada execução; o backward é acumulado.** `load_backward()` carrega do disco as rodadas anteriores, e só os IDs ainda não vistos são buscados.
- **`save()` reescreve os arquivos inteiros.** Por isso, `load_backward()` precisa ser chamado antes de `fetch_backward()` e `save()`: sem ele, o que foi acumulado nas rodadas anteriores é sobrescrito.
- **A etapa 04 pode ser rodada de novo sem refazer trabalho.** Um arquivo válido já baixado não é baixado de novo, o manifesto não toca nas linhas que já existem ao ser gerado, e a extração pula o JSONL que é mais novo que o documento de origem.
- **`status = manual` nunca é sobrescrito.** É o valor para marcar no manifesto um texto recuperado à mão; o download seguinte não altera essa linha.
- **Arquivos são gravados em `.part` e renomeados no final.** Uma queda no meio do download, da extração ou da escrita do manifesto não deixa arquivo corrompido.
- **Texto completo não encontrado nunca significa exclusão.** O work vai para a fila manual, com os links e o motivo da falha de cada candidata.
- **Dentro da fonte `pmc`, o XML é tentado antes do PDF renderizado.** O JATS já traz seções e parágrafos marcados, o que dispensa as heurísticas de layout do PDF.
