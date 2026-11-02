FROM ghcr.io/astral-sh/uv:0.9.11 AS uv
FROM python:3.11-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-cache && \
    mkdir /metrics && chown 10001:10001 /metrics
USER 10001:10001
ENV METRICS_ENV=production METRICS_DB=/metrics/metrics.sqlite3
EXPOSE 8001
CMD ["/app/.venv/bin/uvicorn", "site_directedideation_com.mcp:mcp.http_app", "--factory", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
