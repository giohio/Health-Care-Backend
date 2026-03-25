FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY ["Payment Service/requirements.txt", "./"]
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared libraries
COPY shared /tmp/shared
RUN pip install --no-cache-dir /tmp/shared/healthai-cache \
    && pip install --no-cache-dir /tmp/shared/healthai-common \
    && pip install --no-cache-dir /tmp/shared/healthai-db \
    && pip install --no-cache-dir /tmp/shared/healthai-events

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
