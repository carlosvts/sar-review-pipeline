[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Estrutura

```
data/
  start_set_dois.csv      entrada: coluna `doi`, 16 DOIs do start set
  raw/                    saída da etapa 01: respostas brutas da API
  jsonl/                  saída das etapas 01 a 03: formato de trabalho
  abstracts/              etapa 03: cache das APIs e relatório de cobertura
  cluster/                etapa 03: embeddings, varreduras e atribuições
    <modelo>/             specter2, mpnet ou qwen3 (scincl: análise anterior): embeddings.npy, ids.json, meta.json, umap_2d.npy
      <métrica>/          euclidean ou cosine: sweep.csv, elbow.png, silhouette.png,
                          umap_k*.png, assignments_k*.csv
    human-analysis/       temas dos clusters revisados à mão
  fulltext/               saída da etapa 04
    manifest.csv          uma linha por work, com o estado do download
    manual_queue.csv      works que nenhuma fonte resolveu
    manual_queue.ris      os mesmos works, para importar no Zotero
    docs/                 PDFs e XMLs baixados (W….pdf, W….xml)
    text/                 texto extraído, um JSONL por documento (W….jsonl)
results/                  resultados versionados no git (data/ fica fora do repositório)
  clustering/
    specter2_cosine_k10/  configuração escolhida: assignments_k10.csv, sweep.csv, elbow.png,
                          silhouette.png, umap_k10.png, meta.json, clusters_human_analysis.json
src/sar_review_pipeline/
  work.py                 dataclass Work, normalize_doi, rebuild_abstract, extract_oa_locations
  fetch_metadata/
    parser.py             DoiParser: lê os DOIs do CSV
    api.py                OpenAlexSnowballer: busca, acumula e salva
    __main__.py           ponto de entrada da etapa 01
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
    __main__.py           ponto de entrada da etapa 04
```

Cada etapa é um subpacote de `sar_review_pipeline`. Nomes de pacote Python não podem começar com número, então a etapa 01 se chama `fetch_metadata`, e não `01_fetch_metadata`. A ordem fica registrada nesta tabela e no nome do comando (`step01-fetch`, `step03-abstracts`, `step04-fulltext`).
