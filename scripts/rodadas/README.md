# Scripts das rodadas de snowballing (rodadas 2 e 3)

Scripts de apoio usados em 24/11/2026 para as rodadas 2 e 3, fora do pipeline principal. Eles usam as classes do
pipeline (`Downloader`, `screening`, `AbstractStage`, `Clusterer`, `Inclusion`, `Embedder`) e só trocam os caminhos;
nenhum muda a lógica do pipeline. Rode da raiz do repo com `uv run python scripts/rodadas/<script>.py ...`.

| Script | O que faz |
|---|---|
| `fetch_rodada2.py <csv> <saida.jsonl>` | Busca no OpenAlex os works de uma lista de ids (CSV `openalex_id,...,direction`) e grava um `Work` por linha. |
| `download_rodada2.py <works.jsonl> <resultados.json>` | Roda a cascata do `Downloader` nesses works e grava em `data/fulltext/docs/`, sem tocar em arquivos que já existem. |
| `texto.py extract` / `texto.py chunk <included.jsonl> <chunks.jsonl>` | Extração (`Extractor`) de `data/fulltext/docs/` para `data/fulltext/text/` e chunks (`Chunker`) dos works de uma rodada. Substitui `step04-fulltext extract` e `step05-chunk`, que agora gravam em `data/rounds/`. |
| `check_titles.py <csv>` / `check_one.py <csv> <pdfs...>` | Confere se o título esperado aparece no texto de cada PDF/XML baixado. |
| `write_log.py <pasta> <csv>` | Gera `data/fulltext/rodada2_manual_log.csv` (auto, manual, failed) a partir dos resultados. |
| `merge_artifact.py <data.json> <rodada> <evidence.json> <log.csv> <recs.json>...` | Junta status do texto, evidência do RAG e recomendações de uma rodada no `data.json` do artefato de triagem; só mexe nos artigos dessa rodada. Os failed do log ficam travados com o motivo de EC6. |
| `rag_evidence.py <chunks.jsonl> <evidence.json> <chroma_dir> [coleção]` | Embeddings (Qwen3-Embedding; GPU se houver, senão CPU) e os 3 trechos por QP de cada artigo. A coleção do Chroma é recriada; passe um nome por rodada (padrão `hri-articles-a-rodada2`). |
| `collect_r3.py <seeds.json>` | Coleta da rodada 3: referências e citações (OpenAlex + Semantic Scholar) das sementes, menos o já visto, reconstruído pelo OpenAlex. Grava `data/rodada3/works.jsonl`. Precisa de `OPENALEX_API_KEY` no `.env`. |
| `stages_r3.py title\|abstracts\|sweep\|fit K\|include` | Etapas 02 e 03 da rodada 3 em `data/rodada3/`. `sweep` e `fit` rodam com `--extra cluster-sentence-transformers` e carregam o mpnet em CPU. `include` aplica `data/rodada3/cluster_decision.json`. |

## Estado em 24/11/2026

- Rodada 2: triagem de texto completo concluída (83 de 83). Dados em `data/rodada2/` (zips).
- Rodada 3: coleta, triagem por título, abstracts e clustering (mpnet, K=12) feitos; mantidos os clusters 7, 5 e 8
  (`data/rodada3/cluster_decision.json`), 76 candidatos em `data/rodada3/rodada3_download.csv`.
  Dados completos em `data/rodada3_zip/rodada3_dados.zip` (descompactar dentro de `data/`).
- Rodada 3, texto completo (24/11/2026): 58 de 76 com texto (26 da cascata, 32 manuais pelo Portal CAPES ou em acesso aberto),
  18 failed (EC6). Log em `data/fulltext/rodada3_manual_log.csv`; chunks em `data/fulltext/chunks_r3.jsonl`; RAG em
  `data/fulltext/evidence_r3.json` (coleção `hri-articles-a-rodada3`); recomendações em `data/fulltext/recs_r3.json`.
  Zips em `data/rodada3_zip/` (`rodada3_docs_parte1..3.zip` e `rodada3_texto_rag.zip`; descompactar dentro de
  `data/fulltext/`). Artefato atualizado (versão 6); falta a triagem humana da rodada 3.
- `data/artefato/`: cópia do `data.json` do artefato de triagem e das decisões salvas no banco dele.

## Onde está cada rodada (desde o merge de `wohlin-snowballing`, 24/11/2026)

- Rodadas 0 e 1 (e a coleta e o clustering da rodada 2): pipeline por rodada, em `data/rounds/r0..r2/`, com o
  registro versionado em `results/rounds/r0..r2/` (`uv run record-round --round N`).
- Texto completo da rodada 2 e a rodada 3 em diante: padrão destes scripts, em `data/fulltext/`, `data/rodada2/` e
  `data/rodada3/`. A triagem do texto completo fica no artefato (`data/artefato/`).
- `collect_r3.py` e `stages_r3.py` importam módulos que o merge removeu (`snowball.forward`, `direction`) e não rodam
  mais; precisam ser adaptados antes da rodada 4.
