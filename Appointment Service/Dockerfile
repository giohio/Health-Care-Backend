FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY ["Appointment Service/requirements.txt", "."]
RUN uv pip install --system --no-cache -r requirements.txt

# Copy shared_lib and install it
COPY shared_lib /app/shared_lib
RUN uv pip install --system --no-cache /app/shared_lib

# ==========================================
# STAGE 2: Runtime
# ==========================================
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && groupadd -r appuser && useradd -r -g appuser appuser \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy only this service's code
COPY ["Appointment Service/", "."]
RUN chmod +x scripts/entrypoint.sh && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
