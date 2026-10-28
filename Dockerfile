# Etapa 03 (embeddings e clustering) como job: roda sweep ou fit e termina.
# Uma imagem por extra:
#   docker build --build-arg EXTRA=cluster-specter -t sar-review-pipeline:cluster-specter .
#   docker build --build-arg EXTRA=cluster-sentence-transformers -t sar-review-pipeline:cluster-sentence-transformers .
# data/ e .hf-cache/ nunca entram na imagem: são montados na execução (docker-compose.yml).

# mesma versão do Python do ambiente local (3.12.13), fixada por tag e digest
FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

# mesma versão do uv que gerou o uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded /uv /bin/uv

# obrigatório, sem padrão: cluster-specter ou cluster-sentence-transformers
ARG EXTRA
RUN case "$EXTRA" in \
        cluster-specter|cluster-sentence-transformers) ;; \
        *) echo "EXTRA precisa ser cluster-specter ou cluster-sentence-transformers (recebido: '$EXTRA')" >&2; exit 1 ;; \
    esac

WORKDIR /app

# o uv usa o Python da imagem (nunca baixa outro), copia os arquivos para o .venv
# e não guarda cache de download na imagem (senão cada pacote fica duas vezes nela)
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

# primeiro só as dependências, a partir do lock congelado: esta camada só muda se o lock mudar
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --extra "$EXTRA" --no-install-project

# depois o pacote (o build precisa do README e do src), para existir o comando step03-abstracts
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra "$EXTRA"

# o container roda com o UID do host, sem home real: tudo que precisa gravar vai para /tmp;
# os pesos dos modelos vão para a pasta montada .hf-cache/
ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/.hf-cache \
    HOME=/tmp/home \
    NUMBA_CACHE_DIR=/tmp/numba-cache \
    MPLCONFIGDIR=/tmp/matplotlib

# sem uv run: chama direto o executável do .venv, sem ressincronizar nada na execução
ENTRYPOINT ["/app/.venv/bin/step03-abstracts"]
