# Scripts das rodadas de snowballing (rodada 2 em diante)

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
| `merge_artifact.py <data.json> <rodada> <evidence.json> <log.csv> <recs.json>...` | Junta status do texto, evidência do RAG e recomendações de uma rodada no `data.json` do artefato de triagem; só mexe nos artigos dessa rodada e acrescenta os que faltam (de `data/rodada<N>/included.jsonl`). Os failed do log ficam travados com o motivo de EC6 (data tirada do log). |
| `rag_evidence.py <chunks.jsonl> <evidence.json> <chroma_dir> [coleção]` | Embeddings (Qwen3-Embedding; GPU se houver, senão CPU) e os 3 trechos por QP de cada artigo. A coleção do Chroma é recriada; passe um nome por rodada (padrão `hri-articles-a-rodada2`). |
| `collect_rodada.py <N> <sementes.json>` | Coleta da rodada N: referências e citações (OpenAlex + Semantic Scholar) das sementes, menos o já visto (ids e DOIs dos `works.jsonl` das rodadas anteriores). Grava `data/rodada<N>/works.jsonl`. Precisa de `OPENALEX_API_KEY` e `S2_API_KEY` no `.env`. Era `collect_r3.py` (na rodada 3 o já visto foi reconstruído pelo OpenAlex). |
| `stages_rodada.py <N> title\|abstracts\|sweep\|fit K\|include` | Etapas 02 e 03 da rodada N em `data/rodada<N>/` (o `Round` do pipeline apontado para lá). `sweep` e `fit` rodam com `--extra cluster-sentence-transformers` (GPU se houver). `include` aplica `data/rodada<N>/cluster_decision.json`. Era `stages_r3.py`. |

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

## Estado em 25/11/2026

- Rodada 3: triagem humana concluída (28 include, 5 seed_only); 33 seeds da rodada 4 em `data/rodada4/seeds.json`.
- Rodada 4: 1303 works, 192 candidatos por título, clustering mpnet K=12; mantidos os clusters 0, 3 e 7
  (`data/rodada4/cluster_decision.json`), 48 para texto completo. 41 com texto (15 da cascata ou já no disco, 9 em
  acesso aberto, 17 pelo Portal CAPES), 7 failed (EC6). Log em `data/fulltext/rodada4_manual_log.csv`; RAG em
  `data/fulltext/evidence_r4.json` (coleção `hri-articles-a-rodada4`); recomendações em `data/fulltext/recs_r4.json`.
  Zips em `data/rodada4_zip/` (`rodada4_dados.zip` dentro de `data/`; `rodada4_docs_parte1..2.zip` e
  `rodada4_texto_rag.zip` dentro de `data/fulltext/`). Artefato atualizado (versão 7); falta a triagem humana.

- Rodada 4, triagem humana (25/11/2026): 20 include, 4 seed_only; 24 seeds da rodada 5.
- Rodada 5: 1462 works, 240 candidatos por título, clustering mpnet K=8; mantido só o cluster 5 (reabilitação com SAR;
  só 6% dos candidatos mencionam contexto hospitalar, contra 13% na rodada 4 e 15% na 3, sinal de convergência),
  37 para texto completo. 26 com texto (8 da cascata, 2 em acesso aberto, 16 pelo Portal CAPES), 11 failed (EC6).
  Log em `data/fulltext/rodada5_manual_log.csv`; RAG em `data/fulltext/evidence_r5.json` (coleção
  `hri-articles-a-rodada5`); recomendações em `data/fulltext/recs_r5.json`. Zips em `data/rodada5_zip/`.
  Artefato atualizado (versão 8); falta a triagem humana.

- Rodada 5, triagem humana (25/11/2026): 13 include, 2 seed_only; 15 seeds da rodada 6.
- Rodada 6: 920 works, 132 candidatos por título (4% com contexto hospitalar), clustering mpnet K=7 (testados K=3 e
  K=12); mantido só o cluster 4 (reabilitação com SAR), 22 para texto completo. 17 com texto, 5 failed (EC6).
  Log em `data/fulltext/rodada6_manual_log.csv`; RAG em `data/fulltext/evidence_r6.json`; recomendações em
  `data/fulltext/recs_r6.json`. Zips em `data/rodada6_zip/`. Artefato atualizado (versão 9); falta a triagem humana.

- Rodada 6, triagem humana (25/11/2026): 3 include, 0 seed_only; 3 seeds da rodada 7.
- Rodada 7: 83 works, 13 candidatos por título, 12 com abstract (nenhum com contexto hospitalar explícito); clustering
  mpnet K=5 mantido por rigor; mantido o cluster 2 (SAR para idosos e demência), 5 para texto completo, todos com
  texto. RAG em `data/fulltext/evidence_r7.json`; recomendações em `data/fulltext/recs_r7.json`. Zips em
  `data/rodada7_zip/`. Artefato atualizado (versão 10); falta a triagem humana.

- Rodada 7, triagem humana (25/11/2026): 1 include (W2124717700), 0 seed_only; 1 seed da rodada 8.
- Rodada 8: 260 works, 41 candidatos por título, 36 no clustering (1 com contexto hospitalar); testados K=6 e K=9;
  nenhum cluster mantido (`data/rodada8/cluster_decision.json`), 0 para texto completo. Sem novos artigos, o
  snowballing termina pelo critério de Wohlin. Dados em `data/rodada8_zip/rodada8_dados.zip`.

## Onde está cada rodada (desde o merge de `wohlin-snowballing`, 24/11/2026)

- Rodadas 0 e 1 (e a coleta e o clustering da rodada 2): pipeline por rodada, em `data/rounds/r0..r2/`, com o
  registro versionado em `results/rounds/r0..r2/` (`uv run record-round --round N`).
- Texto completo da rodada 2 e a rodada 3 em diante: padrão destes scripts, em `data/fulltext/`, `data/rodada2/` e
  `data/rodada3/`. A triagem do texto completo fica no artefato (`data/artefato/`).
- `collect_r3.py` e `stages_r3.py` viraram `collect_rodada.py` e `stages_rodada.py`, genéricos por rodada e adaptados ao
  código do merge.
