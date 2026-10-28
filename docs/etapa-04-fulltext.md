[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Etapa 04: `fulltext`

Enquanto a exclusão por cluster da etapa 03 não é decidida, as etapas 04 e 05 rodam sobre uma amostra do backward, e não sobre a lista final de incluídos. Depois da decisão, os clusters mantidos passam a alimentá-las.

A etapa tem dois comandos: o download (`uv run step04-fulltext`) e a extração (`uv run step04-fulltext extract`).

## Download

1. Gera ou completa o `manifest.csv` com os works de `start_set.jsonl` e `backward.jsonl`. Se um ID aparece nos dois, fica o de menor `backward_round`.
2. Sorteia uma amostra reprodutível do backward (`SAMPLE_SIZE = 50`, `SEED = 42`, em `fulltext/__main__.py`).
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

O `Extractor` converte cada arquivo de `data/fulltext/docs/` em parágrafos e grava um JSONL por documento em `data/fulltext/text/`. Essa saída é a entrada do RAG da etapa 05.

- **XML:** segue a marcação do JATS. O abstract entra com a seção `Abstract`; o corpo é percorrido por `<sec>`, incluindo legendas de figuras e tabelas e itens de lista. Notas de rodapé, fórmulas e tabelas embutidas são removidas do texto.
- **PDF (PyMuPDF):** trabalha linha a linha, na ordem de leitura, tratando páginas de duas colunas. Cabeçalhos, rodapés e números de página são removidos, tanto pela margem quanto por se repetirem em várias páginas. Um título de seção precisa ter cara de título (negrito, fonte maior, caixa alta ou fonte própria) e forma de título (numerado, nome conhecido de seção ou linha sozinha). Blocos que são quase só números, como tabelas, são descartados.
- Nos dois formatos, a extração para na bibliografia e pula agradecimentos, financiamento, conflito de interesses, contribuições dos autores, disponibilidade de dados e declaração de ética.
- Documentos com pouco texto (menos de 10 parágrafos ou de 8.000 caracteres), sem texto ou sem nenhuma seção identificada são sinalizados no resumo para conferência manual.

## Arquivos gerados

| Arquivo | Conteúdo |
|---------|----------|
| `data/fulltext/manifest.csv` | uma linha por work, com o estado do download |
| `data/fulltext/docs/W….pdf` ou `W….xml` | texto completo baixado, nomeado pelo ID do OpenAlex |
| `data/fulltext/text/W….jsonl` | um parágrafo por linha |
| `data/fulltext/manual_queue.csv` | works sem texto, com links e motivo da falha; sobrescrito a cada execução |
| `data/fulltext/manual_queue.ris` | os mesmos works, para importar no Zotero e rodar "Find Available PDF" com o acesso institucional (rede ou VPN da UFLA) |

## Colunas de `manifest.csv`

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
