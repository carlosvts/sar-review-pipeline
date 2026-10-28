[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Etapa 03: `abstracts`

A etapa tem duas partes: recuperar o abstract de cada candidato (`fetch`) e agrupar os candidatos por tema (`sweep` e `fit`). Nenhuma parte usa LLM, por decisão do projeto.

## Recuperação de abstracts

A entrada são os candidatos de `data/jsonl/candidates.jsonl` (`passed_title` e `needs_context`), cruzados pelo ID com `data/jsonl/backward.jsonl` para recuperar o `Work` completo. Para cada candidato, a cascata de `AbstractFetcher.SOURCES` para na primeira fonte que devolve um abstract válido:

| # | Fonte | Busca |
|---|-------|-------|
| 1 | `openalex` | o abstract que já veio no registro |
| 2 | `semantic_scholar` | pelo DOI; sem DOI, `search/match` pelo título |
| 3 | `crossref` | pelo DOI; sem DOI, `query.bibliographic` pelo título |
| 4 | `europepmc` | pelo DOI ou pelo título (a Europe PMC indexa o PubMed) |
| 5 | `arxiv` | sempre pelo título |

- **Casamento do registro:** com DOI, cada fonte busca só pelo DOI. Por título, só vale o match com similaridade ≥ `TITLE_MIN_SIMILARITY` (0,95) e o mesmo ano; no arXiv vale também se o DOI informado pelo arXiv for o do work. Abstract errado é pior que nenhum.
- **Validação (`validate.py`):** `ausente` se nenhuma fonte devolveu texto; `invalido` se o texto for boilerplate ("No abstract available", "International audience", aviso de copyright no início) ou tiver menos de `MIN_ABSTRACT_WORDS` (20) palavras. Abstracts válidos com sinais de mistura de metadados (título, autores, palavras-chave, periódico, copyright) recebem flags em `abstract_flags`, sem alteração do texto.
- **Regra de decisão:** `needs_context` sem abstract válido recebe `exclusion_reason = "sem_abstract"` e não segue para o clustering (o registro continua no arquivo, para o PRISMA). `passed_title` sem abstract válido segue com `title_only = true` e entra no clustering só pelo título.
- **Cache:** toda resposta das APIs, inclusive "não encontrado", vai para `data/abstracts/cache/<fonte>.jsonl`. Rodar de novo não refaz chamadas. Erros transitórios (timeout, 429, 5xx) não são guardados e são tentados de novo na execução seguinte.

Campos acrescentados ao `Work` em `data/jsonl/candidates_abstracts.jsonl`, além de `status`, `matched_rule` e `matched_keyword` da triagem por título:

| Campo | Descrição |
|-------|-----------|
| `abstract_status` | `ok`, `ausente` ou `invalido` |
| `abstract_source` | fonte do abstract válido |
| `abstract_match` | `registro`, `doi` ou `titulo` |
| `abstract_flags` | sinais de contaminação: `titulo`, `autores`, `palavras_chave`, `periodico`, `copyright` |
| `title_only` | `true` para `passed_title` sem abstract válido |
| `exclusion_reason` | `"sem_abstract"` para `needs_context` sem abstract válido, senão `null` |

O relatório `data/abstracts/coverage_report.json` traz a cobertura por fonte e por status, a distribuição de tamanho dos abstracts e as listas de suspeitos, rejeitados e erros de API.

## Embeddings e clustering

Entram no clustering os candidatos sem `exclusion_reason`. Cada um vira um vetor normalizado (norma 1, então o produto escalar é o cosseno), com a configuração do modelo em `MODELS` (`embed.py`), seguindo o model card:

- `specter2`: `allenai/specter2_base` com o adapter de proximidade `allenai/specter2`; `título + [SEP] + abstract`, token CLS, até 512 tokens, fp32.
- `mpnet`: `sentence-transformers/all-mpnet-base-v2`; `título + "\n" + abstract`, média dos tokens, até 384 tokens, fp32.
- `qwen3`: `Qwen/Qwen3-Embedding-0.6B`; `título + "\n" + abstract` sem instrução, último token, até 512 tokens, fp16.

Para os `title_only`, o abstract fica vazio. Cada modelo tem o commit do Hugging Face fixado em `MODELS`. O modelo é escolhido na linha de comando, e a geometria por `METRIC` em `cluster.py`: `euclidean` (KMeans do scikit-learn) ou `cosine` (`SphericalKMeans`, com centroides normalizados e atribuição por cosseno). Os embeddings ficam em disco com a configuração completa no `meta.json` e só são reaproveitados se ela, os ids e os textos forem os mesmos.

- `sweep`: para K de 2 a `K_MAX` (30), ajusta o KMeans só nos candidatos com abstract válido e grava inércia e silhouette em `sweep.csv`, `elbow.png` e `silhouette.png`, mais um UMAP para cada K de `UMAP_KS`. O K não é escolhido automaticamente.
- `fit K`: ajusta o KMeans final com os candidatos com abstract; depois, cada `title_only` vai para o centroide mais próximo. Grava `assignments_k{K}.csv` (`id`, `titulo`, `cluster`, `distancia_centroide`, `tem_abstract`, `atribuido_por_titulo`), ordenado por cluster e distância, e o `umap_k{K}.png`.

`SEED = 42` e `N_INIT = 10` ficam no topo de `cluster.py`.

## Resultado atual

- **Abstracts:** 1.201 dos 1.519 candidatos (79,1%) têm abstract válido; o OpenAlex sozinho dava 73,2%. 159 `needs_context` saíram com `sem_abstract` e 159 `passed_title` seguem só pelo título, num total de 1.360 artigos no clustering.
- **Clustering:** SPECTER2 e SciNCL foram testados nas duas geometrias. Euclidiano e cosseno deram resultados quase idênticos. As métricas não separaram os modelos com segurança, e a escolha foi feita pela leitura dos clusters: **SPECTER2, cosseno, K=10**. Os arquivos dessa configuração, com os temas da revisão humana, estão versionados em `results/clustering/specter2_cosine_k10/`. O SciNCL juntava idosos e demência num cluster de 308 artigos, e com K=9 temas diferentes dividiam o mesmo cluster.
- **Pendente:** decidir quais clusters excluir. Os mantidos seguem para a etapa 04.

## Dependências opcionais (extras)

O adapter do SPECTER2 só carrega com a biblioteca `adapters`, que fixa `transformers~=4.57`; os modelos gerais do clustering e o RAG usam `transformers>=5.19`. Por isso as dependências estão em três extras, e `cluster-specter` é declarado no `pyproject.toml` como conflitante com os outros dois (que podem ser instalados juntos):

```bash
uv run --frozen --extra cluster-specter step03-abstracts sweep specter2              # adapters, transformers 4.57, scikit-learn, matplotlib, umap-learn
uv run --frozen --extra cluster-sentence-transformers step03-abstracts sweep mpnet   # sentence-transformers, transformers 5, accelerate, scikit-learn, matplotlib, umap-learn
uv run --frozen --extra rag step05-embed                                             # transformers 5, sentence-transformers, chromadb
```

Modelos válidos no clustering (chaves de `MODELS` em `embed.py`) e o extra de cada um:

| Modelo | Extra | Hugging Face |
|---|---|---|
| `specter2` | `cluster-specter` | `allenai/specter2_base` + adapter `allenai/specter2` |
| `mpnet` | `cluster-sentence-transformers` | `sentence-transformers/all-mpnet-base-v2` |
| `qwen3` | `cluster-sentence-transformers` | `Qwen/Qwen3-Embedding-0.6B` |

Se o extra do modelo pedido não estiver instalado, o comando para com uma mensagem dizendo qual extra usar. O embedding só roda na GPU: sem CUDA, ele para antes de carregar o modelo.

As etapas 01, 02, 04 e a recuperação de abstracts da 03 rodam sem extra.

## Docker

O `sweep` e o `fit` também rodam em container, como um job que roda uma vez e termina. Há um serviço por modelo no `docker-compose.yml`, com `profiles` de mesmo nome. O `specter2` usa a imagem do extra `cluster-specter`; `mpnet` e `qwen3` usam a do `cluster-sentence-transformers`. As imagens são construídas pelo compose a partir do `uv.lock` congelado. `data/` e `.hf-cache/` nunca entram na imagem: são montados do host.

Requisitos: Docker com o Compose, GPU NVIDIA com driver e o [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). Sem GPU, o container falha.

Uma vez em cada máquina, na raiz do projeto:

```bash
cp .env.example .env    # se ainda não existir; preencha HOST_UID e HOST_GID com id -u e id -g
mkdir -p .hf-cache      # cache dos pesos do Hugging Face; precisa existir e ser do seu usuário
```

O container roda com o seu usuário (`HOST_UID:HOST_GID`), para os arquivos gravados em `data/` e `.hf-cache/` ficarem com o seu dono. Sem essas variáveis no `.env`, ou sem as pastas `data/` e `.hf-cache/`, o compose para com erro em vez de rodar como root ou criar a pasta como root.

```bash
docker compose --profile specter2 run --rm specter2                 # sweep specter2 (padrão do serviço)
docker compose --profile specter2 run --rm specter2 fit specter2 10 # KMeans final com K=10
docker compose --profile mpnet run --rm mpnet                       # sweep mpnet
docker compose --profile qwen3 run --rm qwen3                       # sweep qwen3
```

O primeiro `run` de cada serviço constrói a imagem (alguns minutos; ~3,3 GB, quase tudo PyTorch e bibliotecas CUDA). Para reconstruir depois de mudar o código: `docker compose --profile <modelo> build`. Os pesos são baixados para `.hf-cache/` na primeira execução e reaproveitados nas seguintes.
