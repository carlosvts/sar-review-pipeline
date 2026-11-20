[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Estrutura

```
data/
  start_set_dois.csv      entrada: coluna `doi`, 16 DOIs do start set
  rounds/                 pipeline atual (Wohlin), caminhos em rounds.py
    r0/                   start set: raw.jsonl, works.jsonl (seeds da rodada 1)
    r<N>/                 rodada N
      raw.jsonl, works.jsonl, hits.jsonl, unresolved_ids.txt, *_done_seeds.txt, forward_s2_log.jsonl   etapa 01
      title_screening.json(l), candidates.jsonl                                                     etapa 02
      candidates_abstracts.jsonl, coverage_report.json, included.jsonl                              etapa 03
      cluster/<modelo>/   embeddings.npy, ids.json, meta.json, umap_2d.npy
        <métrica>/        sweep.csv, elbow.png, silhouette.png, umap_k*.png, assignments_k*.csv
      fulltext/           manifest.csv, manual_queue.csv/.ris, decisions.csv                         etapa 04
      selected.jsonl      incluídos no texto completo: seeds da rodada N+1
    abstracts_cache/      cache das APIs de abstract (todas as rodadas)
    fulltext/docs/        PDFs e XMLs baixados (W….pdf, W….xml), todas as rodadas
    fulltext/text/        texto extraído, um JSONL por documento (W….jsonl)
    fulltext/chunks.jsonl saída do chunking da etapa 05 (só os selecionados)
    chroma/               etapa 05: banco vetorial do Chroma
  jsonl/, raw/, cluster/, abstracts/, fulltext/   pipeline anterior (histórico, não são mais lidos)
results/                  resultados versionados no git (data/ fica fora do repositório)
  clustering/
    specter2_cosine_k10/  configuração escolhida: assignments_k10.csv, sweep.csv, elbow.png,
                          silhouette.png, umap_k10.png, meta.json, clusters_human_analysis.json
src/sar_review_pipeline/
  work.py                 dataclass Work, normalize_doi, rebuild_abstract, extract_oa_locations
  rounds.py               Round: os arquivos de data/rounds/ de cada rodada e --round
  snowball/               etapa 01
    openalex.py           OpenAlexClient: requisições com retry, paginação por cursor
    semantic_scholar.py   SemanticScholarClient: DOIs de quem cita um artigo (complemento do forward)
    parser.py             DoiParser: lê os DOIs do CSV
    collect.py            fetch_start_set (rodada 0) e RoundCollector: backward e forward de uma rodada
    __main__.py           ponto de entrada da etapa 01 (start, round N)
  screening/
    screening.py          TitleScreeningRule e INCLUSION_RULES: triagem por título e candidates.jsonl (etapa 02)
  abstracts/
    validate.py           AbstractValidator: ok, ausente ou invalido, e flags de suspeita
    fetch.py              AbstractFetcher: cascata de APIs com cache em disco
    stage.py              AbstractStage: junta candidatos e works, regra de decisão, relatório
    embed.py              PaperEmbedder: embeddings specter2, mpnet ou qwen3 (configuração em MODELS)
    cluster.py            Clusterer e SphericalKMeans: varredura de K, ajuste final, UMAP
    __main__.py           ponto de entrada da etapa 03 (fetch, sweep, fit)
  fulltext/
    manifest.py           Manifest: gera e atualiza o manifest.csv
    validate.py           Validator: diz se um arquivo baixado é utilizável
    download.py           Downloader: cascata de fontes e fila manual
    extract.py            Extractor: PDF/XML em parágrafos com seção e página
    __main__.py           ponto de entrada da etapa 04 (download, extract, screen, select)
  rag/
    chunking.py           Chunker: agrupa os parágrafos de cada artigo em chunks por seção (step05-chunk)
    embedds.py            Embedder (Qwen3-Embedding) e ChromaStore: indexa e busca por artigo (step05-embed)
    questions.json        perguntas de pesquisa e sub-queries
```

Cada etapa é um subpacote de `sar_review_pipeline`. Nomes de pacote Python não podem começar com número, então a etapa 01 se chama `snowball`, e não `01_snowball`. Todas as etapas recebem `--round N` e trocam apenas os arquivos (`rounds.py`). A ordem fica registrada nesta tabela e no nome do comando (`step01-snowball`, `step02-screen-titles`, `step03-abstracts`, `step04-fulltext`, `step05-chunk`, `step05-embed`).
