FROM docker.io/library/python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893 AS dependencies
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
COPY staging_mcp/requirements.lock /tmp/requirements.lock
RUN python -m venv "$VIRTUAL_ENV" && \
    pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/requirements.lock

FROM docker.io/library/python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY staging_mcp/server.py staging_mcp/healthcheck.py /app/
COPY src/site_directedideation_com/__init__.py /app/site_directedideation_com/__init__.py
COPY src/site_directedideation_com/metrics.py /app/site_directedideation_com/metrics.py
COPY src/site_directedideation_com/mcp/__init__.py /app/site_directedideation_com/mcp/__init__.py
COPY src/site_directedideation_com/mcp/http_boundary.py /app/site_directedideation_com/mcp/http_boundary.py
USER 10001:10001
EXPOSE 8765
CMD ["uvicorn", "server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765", "--no-access-log", "--log-level", "warning"]
