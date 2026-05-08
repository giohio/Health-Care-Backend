FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; fi \
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 -o Acquire::ForceIPv4=true update \
    && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY ["Payment Service/requirements.txt", "./"]
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared libraries
COPY shared /tmp/shared
RUN pip install --no-cache-dir --no-build-isolation /tmp/shared/uuid-extension \
    && pip install --no-cache-dir --no-build-isolation /tmp/shared/healthai-cache \
    && pip install --no-cache-dir --no-build-isolation /tmp/shared/healthai-db \
    && pip install --no-cache-dir --no-build-isolation /tmp/shared/healthai-common \
    && pip install --no-cache-dir --no-build-isolation /tmp/shared/healthai-events

# Copy payment service
COPY ["Payment Service", "/app/"]

# Create entrypoint script
COPY ["Payment Service/scripts/entrypoint.sh", "/app/scripts/entrypoint.sh"]
RUN chmod +x /app/scripts/entrypoint.sh \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

# Drop root privileges for runtime
USER appuser

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
