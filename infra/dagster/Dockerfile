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
# o que o Dagster le ao carregar as definicoes: a fabrica de assets da bronze le a lista de
# tabelas na DDL, e o asset da planilha abre os arquivos do consolidado
COPY staging/ddl ./staging/ddl
COPY dados/gerencial ./dados/gerencial
# a silver presta contas contra os achados que a auditoria gravou (os números aprovados)
COPY dados/auditoria ./dados/auditoria
RUN uv sync --frozen --no-dev
# a extensao httpfs do DuckDB, pre-instalada: a primeira consulta ao lake nao depende de rede
ENV DUCKDB_EXTENSION_DIRECTORY=/opt/dagster/app/.duckdb
RUN /opt/dagster/venv/bin/python -c "import duckdb; c = duckdb.connect(); c.execute(\"SET extension_directory = '/opt/dagster/app/.duckdb'\"); c.execute('INSTALL httpfs')"

COPY infra/dagster/workspace.yaml ./workspace.yaml

# usuário sem privilégio: o processo nunca roda como root
RUN groupadd --system --gid 10001 dagster \
    && useradd --system --uid 10001 --gid dagster --home-dir /opt/dagster/home dagster \
    && mkdir -p /opt/dagster/home/logs
COPY infra/dagster/dagster.yaml /opt/dagster/home/dagster.yaml
RUN chown -R dagster:dagster /opt/dagster/home

USER dagster
EXPOSE 3000
