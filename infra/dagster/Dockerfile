# Imagem do Dagster com o código do projeto. Usada pelo webserver e pelo daemon.
FROM python:3.12.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

ENV DAGSTER_HOME=/opt/dagster/home \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/dagster/venv \
    PATH=/opt/dagster/venv/bin:$PATH

WORKDIR /opt/dagster/app

# dependências primeiro (camada em cache enquanto o lock não muda), código depois
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

COPY infra/dagster/workspace.yaml ./workspace.yaml

# usuário sem privilégio: o processo nunca roda como root
RUN groupadd --system --gid 10001 dagster \
    && useradd --system --uid 10001 --gid dagster --home-dir /opt/dagster/home dagster \
    && mkdir -p /opt/dagster/home/logs
COPY infra/dagster/dagster.yaml /opt/dagster/home/dagster.yaml
RUN chown -R dagster:dagster /opt/dagster/home

USER dagster
EXPOSE 3000
