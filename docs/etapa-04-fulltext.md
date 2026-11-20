[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Etapa 04: `fulltext`

A etapa roda por rodada, sobre os artigos dos clusters mantidos na etapa 03 (`r<N>/included.jsonl`, gerado por `uv run step03-abstracts include --round N`). A rodada 0 é o start set.

Comandos:

- `uv run step04-fulltext download --round N`: baixa o texto completo dos incluídos da rodada.
- `uv run step04-fulltext extract`: extrai o texto de tudo que já foi baixado, em todas as rodadas (`--force` extrai de novo mesmo o que já foi extraído).
- `uv run step04-fulltext screen --round N`: gera ou completa `r<N>/fulltext/decisions.csv` para a leitura do texto completo.
- `uv run step04-fulltext select --round N`: grava `r<N>/selected.jsonl`, que são os seeds da rodada N+1.

## Download

1. Gera ou completa o `r<N>/fulltext/manifest.csv` com os works de `r<N>/included.jsonl`. Sem o `included.jsonl`, o comando para e pede o `include` da etapa 03.
3. Para cada work, percorre a cascata de fontes e fica com o primeiro arquivo que baixar e validar.
4. Imprime um resumo: quantos têm texto, por fonte, por tipo, e o motivo de cada falha.
5. Grava o resultado de cada work no manifesto.
6. Exporta a fila manual com o que nenhuma fonte resolveu.

## Cascata de fontes

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

## Validação

O `Validator` identifica o tipo pelos primeiros bytes do arquivo, sem confiar na extensão nem no `Content-Type`.

- **PDF:** começa com `%PDF-`, tem pelo menos 10 KB e traz `%%EOF` no final.
- **XML (JATS):** bem formado, com um `<article>` na raiz ou dentro de `<pmc-articleset>`, e um `<body>` com pelo menos 2.000 caracteres.
- **HTML** é rejeitado com o motivo "paywall ou bloqueio?".

## Extração

O `Extractor` converte cada arquivo de `data/rounds/fulltext/docs/` em parágrafos e grava um JSONL por documento em `data/rounds/fulltext/text/`. O RAG da etapa 05 usa só os textos dos selecionados (start set e `selected.jsonl` de cada rodada).

- **XML:** segue a marcação do JATS. O abstract entra com a seção `Abstract`; o corpo é percorrido por `<sec>`, incluindo legendas de figuras e tabelas e itens de lista. Notas de rodapé, fórmulas e tabelas embutidas são removidas do texto.
- **PDF (PyMuPDF):** trabalha linha a linha, na ordem de leitura, tratando páginas de duas colunas. Cabeçalhos, rodapés e números de página são removidos, tanto pela margem quanto por se repetirem em várias páginas. Um título de seção precisa ter cara de título (negrito, fonte maior, caixa alta ou fonte própria) e forma de título (numerado, nome conhecido de seção ou linha sozinha). Blocos que são quase só números, como tabelas, são descartados.
- Nos dois formatos, a extração para na bibliografia e pula agradecimentos, financiamento, conflito de interesses, contribuições dos autores, disponibilidade de dados e declaração de ética.
- Documentos com pouco texto (menos de 10 parágrafos ou de 8.000 caracteres), sem texto ou sem nenhuma seção identificada são sinalizados no resumo para conferência manual.

## Arquivos gerados

| Arquivo | Conteúdo |
|---------|----------|
| `data/rounds/fulltext/docs/W….pdf` ou `W….xml` | texto completo baixado, nomeado pelo ID do OpenAlex (comum a todas as rodadas) |
| `data/rounds/fulltext/text/W….jsonl` | um parágrafo por linha |
| `r<N>/fulltext/manifest.csv` | uma linha por work da rodada, com o estado do download |
| `r<N>/fulltext/manual_queue.csv` | works sem texto, com links e motivo da falha; sobrescrito a cada execução |
| `r<N>/fulltext/manual_queue.ris` | os mesmos works, para importar no Zotero e rodar "Find Available PDF" com o acesso institucional (rede ou VPN da UFLA) |

## Decisão do texto completo

Wohlin: só o que passa no texto completo vira seed da rodada seguinte. A decisão segue os critérios do protocolo ([criterios-elegibilidade.md](criterios-elegibilidade.md)). O RAG da etapa 05 (`step05-chunk` e `step05-embed --round N`) grava, por artigo, os 3 trechos mais próximos de cada QP em `r<N>/fulltext/rag_review/W….md`, com seção e página; a leitura é humana. O `screen` gera `r<N>/fulltext/decisions.csv`, uma linha por incluído no cluster, com `id`, `doi`, `title`, `publication_year`, `direction`, `text_status` e `local_path` (do manifesto), as colunas `qp1` a `qp5` (`sim`/`não`), `decision` e `reason`.

- `decision` aceita `include` (entra na síntese e vira seed), `seed_only` (revisão ou estudo secundário, EC4: fora da síntese, mas vira seed, como o protocolo permite) e `exclude`. `reason` leva o código do critério (ex.: `EC6`).
- Só QP1 a QP4 (as quatro dimensões de IC3) incluem; a QP5 (desafios) é apoio. Com `decision` vazia e QP1 a QP4 preenchidas, vale `include` se alguma for `sim`, senão `exclude` (EC3).
- O start set (rodada 0) passa pelos mesmos critérios: `screen`, `step05-chunk`, `step05-embed` e `select --round 0`. Ele já foi seed da rodada 1 inteiro; o `select` da rodada 0 só define a síntese.

Rodar o `screen` de novo (depois da fila manual, por exemplo) atualiza `text_status` e `local_path`, mas nunca apaga uma decisão.

O `select` para se alguma linha estiver sem decisão válida. Com tudo decidido, grava os `include` em `r<N>/synthesis.jsonl` e os `include` + `seed_only` em `r<N>/selected.jsonl` (os seeds da rodada seguinte). Sem nenhum seed, o snowballing convergiu.

Um work sem texto completo (fila manual) é buscado à mão pela UFLA; o arquivo vai para `data/rounds/fulltext/docs/W….pdf` e a linha do manifesto vira `manual`, com o nome do arquivo original em `note`. O que nem assim aparece sai com `exclude` e `EC6`.

## Colunas de `manifest.csv`

| Coluna | Descrição |
|--------|-----------|
| `id`, `doi`, `title`, `publication_year`, `round` | copiados do `Work` |
| `n_pdf_candidates` | quantas `oa_locations` têm `pdf_url` |
| `n_landing_only` | quantas `oa_locations` têm só `landing_page_url` |
| `status` | `pending`, `downloaded`, `failed` ou `manual` |
| `source_used` | fonte da cascata que resolveu o work |
| `url_used` | URL de onde o arquivo foi baixado |
| `kind` | `pdf` ou `xml` |
| `local_path` | caminho do arquivo em `data/rounds/fulltext/docs/` |
| `note` | motivo da falha, quando `status = failed` |

## Campos de `text/W….jsonl`

| Campo | Descrição |
|-------|-----------|
| `id` | ID do OpenAlex (URL completa) |
| `key` | ID curto, igual ao nome do arquivo (`W123`) |
| `kind` | `pdf` ou `xml` |
| `para` | índice do parágrafo no documento, a partir de 0 |
| `section` | caminho da seção (`2 Methods > 2.1 Participants`), ou `""` se não identificada |
| `page` | página no PDF, a partir de 1; `null` para XML |
| `text` | texto do parágrafo |
