#!/bin/sh
set -e

# Wait for database
echo "Waiting for database..."
until pg_isready -h postgres -p 5432 -U ${POSTGRES_USER:-postgres}; do
  echo "Database is unavailable - sleeping"
  sleep 1
done

echo "Running database migrations..."
# Auto-generate migration from models if no migration files exist
if [ -z "$(ls -A /app/alembic/versions/*.py 2>/dev/null)" ]; then
  echo "No migration files found, generating from models..."
  alembic revision --autogenerate -m "initial"
fi
alembic upgrade head

echo "Starting application..."
exec "$@"
