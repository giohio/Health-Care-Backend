FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY ["Notification Service/requirements.txt", "."]
RUN uv pip install --system --no-cache -r requirements.txt

COPY shared /tmp/shared
RUN uv pip install --system --no-cache /tmp/shared/healthai-cache \
    && uv pip install --system --no-cache /tmp/shared/healthai-common \
    && uv pip install --system --no-cache /tmp/shared/healthai-db \
    && uv pip install --system --no-cache /tmp/shared/healthai-events

FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && groupadd -r appuser && useradd -r -g appuser appuser \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY ["Notification Service/", "."]
COPY shared/healthai-tracing /shared/healthai-tracing
RUN chmod +x /app/scripts/entrypoint.sh && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
