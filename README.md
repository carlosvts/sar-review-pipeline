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

O snowballing segue o Wohlin: em cada rodada, os selecionados da rodada anterior passam por backward e forward juntos, e só o que passa na triagem completa (título, abstract e cluster, texto completo) vira seed da rodada seguinte. Tudo fica em `data/rounds/`.

```bash
# rodada 0: start set
uv run step01-snowball start
uv run step04-fulltext download --round 0

# rodada N (N = 1, 2, ...), até uma rodada não selecionar nenhum artigo
uv run step01-snowball round N                    # 01-02. backward + forward e triagem por título
uv run step03-abstracts fetch --round N           # 03. abstracts
uv run --frozen --extra cluster-sentence-transformers step03-abstracts sweep mpnet --round N
uv run --frozen --extra cluster-sentence-transformers step03-abstracts fit mpnet K --round N
#   decisão humana: K e clusters excluídos em DECISIONS[N] (abstracts/include.py)
uv run step03-abstracts include --round N
uv run step04-fulltext download --round N         # 04. texto completo (+ fila manual pela rede da UFLA)
uv run step04-fulltext screen --round N           #   decisão humana: decision/reason em r<N>/fulltext/decisions.csv
uv run step04-fulltext select --round N           #   r<N>/selected.jsonl = seeds da rodada N+1

# depois da última rodada
uv run step04-fulltext extract
uv run step05-chunk
uv run --frozen --extra rag step05-embed
```

## Documentação

- [Fluxo da pipeline](docs/pipeline-fluxo.md)
- Etapas: [01 snowballing](docs/etapa-01-fetch-metadata.md) · [02 título](docs/etapa-02-triagem-titulo.md) · [03 abstracts e clustering](docs/etapa-03-abstracts.md) · [04 texto completo](docs/etapa-04-fulltext.md)
- [Estrutura do código e de `data/`](docs/estrutura.md)
- [Decisões de projeto](docs/decisoes.md)
