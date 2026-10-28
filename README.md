# sar-review-pipeline

Pipeline em Python para automatizar uma revisão sistemática com snowballing sobre robôs socialmente assistivos (SARs), desenvolvida na UFLA.

O snowballing backward manual gerou artigos demais para triar à mão. O pipeline automatiza a coleta e a triagem, mantendo um humano na decisão final.

## Etapas

| # | Etapa | Estado | Detalhes |
|---|-------|--------|----------|
| 01 | Buscar no OpenAlex os metadados do start set e das referências (backward), rodada a rodada até a fronteira esvaziar | implementada | [docs](docs/etapa-01-fetch-metadata.md) |
| 02 | Cortar por título, registrando a regra que cortou cada artigo | implementada (regras da execução 5) | [docs](docs/etapa-02-triagem-titulo.md) |
| 03 | Triar os sobreviventes pelo abstract, buscando em outra fonte quando o OpenAlex não o trouxer, e agrupá-los por tema para a exclusão por cluster | implementada; falta decidir quais clusters excluir | [docs](docs/etapa-03-abstracts.md) |
| 04 | Baixar o texto completo dos incluídos e extrair o texto em parágrafos | implementada; roda hoje sobre uma amostra | [docs](docs/etapa-04-fulltext.md) |
| 05 | RAG: recuperar, em cada artigo, o trecho que mais provavelmente responde a cada pergunta de pesquisa | implementada: chunking, embeddings e busca por artigo no Chroma, testados numa amostra | |
| 06 | Supervisão humana: sim ou não para cada resposta | planejada | |
| 07 | Tabela final redigida por LLM e análise estatística em pandas | planejada | |

A organização das pastas e do código está em [docs/estrutura.md](docs/estrutura.md), e as decisões de projeto em [docs/decisoes.md](docs/decisoes.md).

## Configuração

Requer [uv](https://docs.astral.sh/uv/) e Python 3.12 ou superior. Rode sempre da raiz do projeto: os caminhos `data/...` são relativos ao diretório atual.

```bash
uv sync
cp .env.example .env   # e preencha as variáveis
```

Variáveis do `.env`:

- `OPENALEX_API_KEY`: chave do OpenAlex (etapa 01).
- `S2_API_KEY`: opcional; se existir, é enviada ao Semantic Scholar para aumentar o limite de requisições.
- `CONTACT_EMAIL`: e-mail de contato enviado à Crossref (polite pool) e no User-Agent das APIs da etapa 03.
- `HOST_UID` e `HOST_GID`: só para o Docker; o resultado de `id -u` e `id -g`.

## Como rodar

```bash
# etapas 01 e 02: snowballing completo, busca + triagem por título rodada a rodada até a fronteira esvaziar
uv run step01-snowball
uv run python -m sar_review_pipeline.main             # equivalente

# só uma rodada de cada etapa, separadamente
uv run step01-fetch                                   # start set + rodada 1 do backward
uv run step02-screen-titles                           # triagem por título do que já foi baixado

# etapa 03: recupera e valida o abstract dos candidatos
uv run step03-abstracts fetch
uv run step03-abstracts fetch --sample 60   # amostra reprodutível

# etapa 04: baixa o texto completo (amostra do backward) e extrai o texto
uv run step04-fulltext
uv run step04-fulltext extract
uv run step04-fulltext extract --force      # extrai de novo, mesmo o que já foi extraído

# etapa 05: RAG (o chunking lê a saída do extract e vem antes dos embeddings)
uv run step05-chunk                         # data/fulltext/text/ -> data/fulltext/chunks.jsonl
uv run --frozen --extra rag step05-embed    # embeddings dos chunks no Chroma (data/chroma/) e teste de busca
```

A etapa 03 tem duas partes: o `fetch` acima e o clustering abaixo, que roda depois dele.

### Etapa 03: embeddings e clustering

O modelo é obrigatório. Cada um roda no seu extra, e o embedding só roda na GPU:

| Modelo | Extra |
|---|---|
| `specter2` | `cluster-specter` |
| `mpnet` | `cluster-sentence-transformers` |
| `qwen3` | `cluster-sentence-transformers` |

```bash
uv run --frozen --extra cluster-specter step03-abstracts sweep specter2   # cotovelo, silhouette e UMAP de K=2 a 30
uv run --frozen --extra cluster-specter step03-abstracts fit specter2 10  # KMeans final com o K escolhido
uv run --frozen --extra cluster-sentence-transformers step03-abstracts sweep mpnet
uv run --frozen --extra cluster-sentence-transformers step03-abstracts sweep qwen3
```

#### Com Docker

Requer Docker com o Compose, GPU NVIDIA com driver e o [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). Uma vez em cada máquina:

```bash
# no .env: HOST_UID e HOST_GID (id -u e id -g)
mkdir -p .hf-cache   # cache dos pesos do Hugging Face, com o seu usuário
```

```bash
docker compose --profile specter2 run --rm specter2                  # sweep specter2
docker compose --profile specter2 run --rm specter2 fit specter2 10  # KMeans final com o K escolhido
docker compose --profile mpnet run --rm mpnet                        # sweep mpnet
docker compose --profile qwen3 run --rm qwen3                        # sweep qwen3
```

O primeiro `run` de cada serviço constrói a imagem. Depois de mudar o código: `docker compose --profile <modelo> build`. Detalhes do container em [docs/etapa-03-abstracts.md](docs/etapa-03-abstracts.md#docker).
