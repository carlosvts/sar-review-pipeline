# Scripts das rodadas de snowballing (rodadas 2 e 3)

Scripts de apoio usados em 24/11/2026 para as rodadas 2 e 3, fora do pipeline principal. Eles usam as classes do
pipeline (`Downloader`, `screening`, `AbstractStage`, `Clusterer`, `Inclusion`, `Embedder`) e só trocam os caminhos;
nenhum muda a lógica do pipeline. Rode da raiz do repo com `uv run python scripts/rodadas/<script>.py ...`.

| Script | O que faz |
|---|---|
| `fetch_rodada2.py <csv> <saida.jsonl>` | Busca no OpenAlex os works de uma lista de ids (CSV `openalex_id,...,direction`) e grava um `Work` por linha. |
| `download_rodada2.py <works.jsonl> <resultados.json>` | Roda a cascata do `Downloader` nesses works, sem tocar em arquivos que já existem em `data/fulltext/docs/`. |
| `check_titles.py <csv>` / `check_one.py <csv> <pdfs...>` | Confere se o título esperado aparece no texto de cada PDF/XML baixado. |
| `write_log.py <pasta> <csv>` | Gera `data/fulltext/rodada2_manual_log.csv` (auto, manual, failed) a partir dos resultados. |
| `merge_artifact.py <pasta>` | Junta status do texto, evidência do RAG e recomendações no `data.json` do artefato de triagem. |
| `rag_evidence.py <chunks.jsonl> <evidence.json> <chroma_dir>` | Embeddings (Qwen3-Embedding; GPU se houver, senão CPU) e os 3 trechos por QP de cada artigo. |
| `collect_r3.py <seeds.json>` | Coleta da rodada 3: referências e citações (OpenAlex + Semantic Scholar) das sementes, menos o já visto, reconstruído pelo OpenAlex. Grava `data/rodada3/works.jsonl`. Precisa de `OPENALEX_API_KEY` no `.env`. |
| `stages_r3.py title\|abstracts\|sweep\|fit K\|include` | Etapas 02 e 03 da rodada 3 em `data/rodada3/`. `sweep` e `fit` rodam com `--extra cluster-sentence-transformers` e carregam o mpnet em CPU. `include` aplica `data/rodada3/cluster_decision.json`. |

## Estado em 24/11/2026

- Rodada 2: triagem de texto completo concluída (83 de 83). Dados em `data/rodada2/` (zips).
- Rodada 3: coleta, triagem por título, abstracts e clustering (mpnet, K=12) feitos; mantidos os clusters 7, 5 e 8
  (`data/rodada3/cluster_decision.json`), 76 candidatos em `data/rodada3/rodada3_download.csv`.
  Dados completos em `data/rodada3_zip/rodada3_dados.zip` (descompactar dentro de `data/`).
- Próximo passo da rodada 3: texto completo (cascata + manual pelo Portal CAPES), extração, chunks, RAG e triagem.
- `data/artefato/`: cópia do `data.json` do artefato de triagem e das decisões salvas no banco dele.
