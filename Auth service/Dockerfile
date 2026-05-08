# ==========================================
# STAGE 1: Builder — install dependencies only
# Using python:3.10-slim keeps base image lightweight
# ==========================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install build-time system deps
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; fi \
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 -o Acquire::ForceIPv4=true update \
    && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
RUN pip install --no-cache-dir --upgrade "setuptools>=70.0.0" "wheel>=0.46.2" "jaraco.context>=6.1.0" uv

# Copy only dependency files first
COPY ["Auth service/requirements.txt", "."]
RUN uv pip install --system --no-cache --no-build-isolation -r requirements.txt

# Install shared packages used across services
COPY shared /tmp/shared
RUN uv pip install --system --no-cache --no-build-isolation /tmp/shared/uuid-extension \
    && uv pip install --system --no-cache --no-build-isolation /tmp/shared/healthai-cache \
    && uv pip install --system --no-cache --no-build-isolation /tmp/shared/healthai-db \
    && uv pip install --system --no-cache --no-build-isolation /tmp/shared/healthai-common \
    && uv pip install --system --no-cache --no-build-isolation /tmp/shared/healthai-events

# ==========================================
# STAGE 2: Runtime — minimal production image
# ==========================================
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Install runtime OS packages and setup security
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; fi \
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 -o Acquire::ForceIPv4=true update \
    && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && groupadd -r appuser && useradd -r -g appuser appuser \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code and setup permissions
COPY ["Auth service/", "."]
COPY shared/healthai-tracing /shared/healthai-tracing
RUN chmod +x scripts/entrypoint.sh && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Port (Auth Service usually 8000)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Entrypoint
ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]

# Default command (Check if main.py or similar exists)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]


