# Tarefa: texto completo, RAG e triagem da rodada 3 do snowballing (sar-review-pipeline)

Estou no meu PC de casa (com GPU). O trabalho da rodada 3 parou antes do texto completo, num notebook da UFLA.
Tudo está no GitHub, na branch `forward-snowballing` (commit `4b1de06` ou mais novo). O foco da revisão é
**SARs (robôs socialmente assistivos) na saúde, especialmente em hospitais**.

Trabalhe em etapas. Pare ao fim de cada etapa, mostre o que fez e espere eu mandar seguir. Não mude a lógica do
pipeline sem me perguntar. Se precisar decidir algo que não está aqui, pergunte. Commits e PRs **sem** autoria ou
coautoria do Claude.

## Contexto

- As "rodadas" são feitas no nível do texto completo: as sementes da rodada N são os include + seed_only (EC4) da
  rodada N-1, nas duas direções (referências e citações).
- Rodada 3 até agora: 2.169 works coletados → 365 pela triagem por título → 304 com abstract → clustering mpnet K=12 →
  mantidos os clusters 7 (pediatria hospitalar), 5 (design de robôs terapêuticos) e 8 (reabilitação pediátrica) →
  **76 candidatos** (`data/rodada3/rodada3_download.csv`; decisão em `data/rodada3/cluster_decision.json`).
- Os scripts de apoio das rodadas 2 e 3 estão em `scripts/rodadas/` (leia o `README.md` de lá). Eles usam as classes
  do pipeline e só trocam caminhos.
- Artefato de triagem (claude.ai): https://claude.ai/artifact/LTATetD8xn41xgkqWazyxD ("Triagem SAR Hospitais").
  A rodada 3 já aparece lá com os 76 candidatos, sem texto completo, sem trechos do RAG e sem recomendação.
  Cópia do conteúdo em `data/artefato/`.

## Etapa 1: preparar o repositório

1. `git status`. Se houver mudanças locais ou commits não enviados, pare e me mostre, sem descartar nada.
2. `git fetch`, `git checkout forward-snowballing`, `git pull --ff-only`.
3. Descompacte: `data/rodada2/rodada2_docs_parte1.zip`, `rodada2_docs_parte2.zip` e `rodada2_dados.zip` dentro de
   `data/fulltext/`; `data/rodada3_zip/rodada3_dados.zip` dentro de `data/`. Confira que `data/fulltext/docs/` tem os
   70 textos da rodada 2 e que `data/rodada3/included.jsonl` tem 76 linhas.
4. Confira que o `.env` tem `OPENALEX_API_KEY` e `S2_API_KEY` preenchidos (sem me mostrar os valores). Sem a chave, o
   OpenAlex usa uma cota compartilhada que acaba rápido.
5. `uv sync --extra rag` e confira que a GPU aparece: `uv run --extra rag python -c "import torch; print(torch.cuda.is_available())"`.

## Etapa 2: cascata automática

1. Rode a cascata do `Downloader` nos 76:
   `uv run python scripts/rodadas/download_rodada2.py data/rodada3/included.jsonl <pasta-temporária>/rodada3_results.json`
   Ele não sobrescreve arquivos que já existem em `data/fulltext/docs/`.
2. Confira cada arquivo baixado com `scripts/rodadas/check_one.py` (o título do CSV tem de aparecer no texto; aponte
   PDFs de 1–2 páginas, que podem ser resumo ou editorial, e documentos enormes, que podem ser tese).
3. Me diga quantos foram baixados, de quais fontes, por `direction`, e quais ficaram para o manual.

## Etapa 3: download manual no Chrome (Claude in Chrome)

Só com os que a cascata não pegou. Pode orquestrar um agente Haiku para a navegação, mas confira o que ele trouxer.

- **Caminho que funcionou na rodada 2: o proxy do Portal de Periódicos da CAPES**, com a minha sessão CAFe da UFLA
  já aberta no Chrome. Abra `https://ez26.periodicos.capes.gov.br/login?url=https://doi.org/<DOI>`: o proxy leva para a
  editora com acesso da UFLA e evita o captcha do ScienceDirect. Se o proxy pedir login, pare e me chame.
- **Como salvar sem travar:**
  - SAGE e ACM: navegue para o link direto com download (`.../doi/pdf/<DOI>?download=true`); o arquivo cai sozinho em
    `~/Downloads`.
  - Páginas em acesso aberto do mesmo site (MDPI, Ovid OA, repositórios): `fetch` do PDF dentro da página e um `<a download>`
    com `{openalex_id}.pdf` também funcionam, mas o Chrome bloqueia o segundo download automático do mesmo site.
  - Springer, IEEE (`/stampPDF/getPDF.jsp?tp=&arnumber=<n>`), Elsevier (`.../pii/<PII>/pdfft?isDTMRedirect=true&download=true`),
    OUP, AAP, Emerald, APA: o PDF abre no visualizador do Chrome. Espere carregar (uns 15 s), clique no ícone de download
    do visualizador e **me avise para eu clicar em Salvar** na janela do sistema (você não consegue ver nem clicar nela).
    Se em 1 minuto o arquivo não chegar, a janela não apareceu: clique de novo.
- **Fontes permitidas:** site da editora, Portal CAPES, PMC/Europe PMC, arXiv, repositórios institucionais.
- **Fontes proibidas:** Sci-Hub, LibGen, Anna's Archive, Z-Library ou espelhos. O relatório tem de dizer de onde veio
  cada texto.
- Nunca digite credenciais. Não resolva captcha. Não compre nada.
- Antes de salvar, confira que o título bate com o CSV e que não é página de bloqueio nem só o abstract. Salve em
  `data/fulltext/docs/{openalex_id}.pdf`.
- Sem acesso nem pela editora nem pela CAPES (na rodada 2: capítulos de livro Springer, Wiley, T&F, AIP, DBpia):
  marque `failed`. Eu excluo esses por EC6.

## Etapa 4: registro

Crie `data/fulltext/rodada3_manual_log.csv` com `openalex_id, direction, status (auto | manual | failed), fonte, url, data,
justificativa, title, doi_url`. Os manuais levam a justificativa "recuperado manualmente" e, se for o caso, a fonte
"via Portal CAPES (CAFe UFLA)". Os failed levam "EC6: <motivo>". Me mostre os números por `direction` e por fonte.

## Etapa 5: extração, chunks e RAG (na GPU)

1. `uv run step04-fulltext extract` e `uv run step05-chunk`. Aponte documentos com pouco texto extraído (na rodada 2, um
   PDF da Elsevier com cada palavra num bloco separado virou só 566 caracteres).
2. `uv run --extra rag python scripts/rodadas/rag_evidence.py data/fulltext/chunks.jsonl data/fulltext/evidence_r3.json data/chroma`
   (Qwen3-Embedding na GPU; 3 trechos por QP, QP1 a QP4, com o maior cosseno entre o trecho e as sub-queries da QP).
3. Confira que todos os artigos da rodada 3 com texto aparecem no `evidence_r3.json`.

## Etapa 6: recomendações e artefato

1. Para cada artigo da rodada 3 com texto, escreva uma recomendação de triagem a partir dos trechos e do abstract,
   no formato do artefato: `{decision: include|seed_only|exclude|unsure, code, qp: {QP1..QP4}, why (1 frase em português),
   confidence: alta|média|baixa, basis: "rag"}`. Critérios: include se responde a alguma QP com evidência concreta;
   seed_only/EC4 para revisões e estudos secundários; exclude EC1 (sem componente social), EC2 (puramente técnico),
   EC3 (não responde às QPs), EC5 (resumo, pôster, editorial), IC6 (não revisado por pares: tese, dissertação, preprint).
   Pode dividir em lotes entre subagentes.
2. Atualize o artefato só na rodada 3: `text_status` (downloaded | manual | failed), `evidence`, `rec`; os failed ficam
   `locked: true` com `locked_reason` de EC6. Antes de publicar, leia a versão atual do artefato e não mexa nas outras
   rodadas nem nas decisões salvas no banco dele (coleção `decisions`). O script `scripts/rodadas/merge_artifact.py`
   mostra como foi feito na rodada 2.
3. Me passe o link e os números.

## Etapa 7: commit

Siga a regra do repo: o que outro PC vai precisar vai para o GitHub (em zip se for grande). Zipe os textos da rodada 3,
o texto extraído, o `chunks.jsonl`, o `evidence_r3.json` e o log, e commite na `forward-snowballing` com `git add -f`
(o `data/` está no `.gitignore`). Sem autoria do Claude. Push só depois que eu mandar.

Depois que eu fizer a triagem da rodada 3 no artefato, a próxima rodada segue o mesmo fluxo (coleta com
`scripts/rodadas/collect_r3.py` adaptado, título, abstracts, clustering parando para eu ver silhueta e cotovelo,
inclusão, texto completo, RAG), até uma rodada não trazer artigos novos.

## Estilo, se precisar mexer em código

Siga o estilo do repo: classes com classmethods, laços `for` simples e um `main` só para orquestrar. Não empilhe
comprehensions na mesma linha. Funções de contagem devolvem um dicionário em vez de imprimir.
