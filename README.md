# sar-review-pipeline

Pipeline em Python que automatiza a coleta e a triagem de uma revisão sistemática por snowballing sobre robôs socialmente assistivos (SARs), desenvolvida na UFLA. As decisões de inclusão continuam humanas.

## Configuração

Requer [uv](https://docs.astral.sh/uv/) e Python 3.12 ou superior.

```bash
uv sync
cp .env.example .env   # e preencha as chaves
```

Rode sempre da raiz do projeto.

## Como rodar

```bash
# 01-02. snowballing com triagem por título
uv run step01-snowball               # backward
uv run step01-snowball forward       # forward, depois da etapa 03 do backward

# 03. abstracts, clustering e exclusão por cluster
uv run step03-abstracts fetch
uv run --frozen --extra cluster-sentence-transformers step03-abstracts sweep mpnet
uv run --frozen --extra cluster-sentence-transformers step03-abstracts fit mpnet 10
uv run step03-abstracts include

# 04. texto completo
uv run step04-fulltext
uv run step04-fulltext extract

# 05. RAG
uv run step05-chunk
uv run --frozen --extra rag step05-embed
```

Para o forward, as etapas 02 e 03 recebem `--direction forward`.

## Documentação

- [Fluxo da pipeline](docs/pipeline-fluxo.md)
- Etapas: [01 snowballing](docs/etapa-01-fetch-metadata.md) · [02 título](docs/etapa-02-triagem-titulo.md) · [03 abstracts e clustering](docs/etapa-03-abstracts.md) · [04 texto completo](docs/etapa-04-fulltext.md)
- [Estrutura do código e de `data/`](docs/estrutura.md)
- [Decisões de projeto](docs/decisoes.md)
