FROM python:3.11-slim AS dependencies
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
COPY requirements.lock /tmp/requirements.lock
RUN python -m venv "$VIRTUAL_ENV" && \
    pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/requirements.lock

FROM python:3.11-slim
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY server.py healthcheck.py /app/
USER 10001:10001
EXPOSE 8765
CMD ["uvicorn", "server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765", "--no-access-log", "--log-level", "warning"]
