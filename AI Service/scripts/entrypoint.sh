#!/bin/sh
set -eu

# Suppress Matplotlib permission warnings
export MPLCONFIGDIR=/tmp/matplotlib

echo "Waiting for database..."
until pg_isready -h postgres -p 5432 -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1; do
  echo "Database is unavailable - sleeping"
  sleep 1
done

PSQL_DATABASE_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+asyncpg|postgresql|')

has_migration_files() {
  if [ -n "$(find /app/alembic/versions -maxdepth 1 -type f -name '*.py' ! -name '__init__.py' -print -quit 2>/dev/null)" ]; then
    return 0
  fi
  return 1
}

create_initial_migration() {
  mkdir -p /app/alembic/versions
  echo "No migration files found, generating initial migration..."
  if ! alembic revision --autogenerate -m "initial" >/tmp/alembic_revision.log 2>&1; then
    if grep -qE "Can't locate revision identified by|Target database is not up to date" /tmp/alembic_revision.log; then
      echo "Detected stale or out-of-sync Alembic revision. Resetting and retrying..."
      psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 -c "DROP TABLE IF EXISTS alembic_version;"
      alembic revision --autogenerate -m "initial"
    else
      cat /tmp/alembic_revision.log
      exit 1
    fi
  fi
  return 0
}

upgrade_head() {
  alembic upgrade head
  return $?
}

echo "Running database migrations..."
if [ -d /app/alembic ]; then
  if ! has_migration_files; then
    create_initial_migration
  fi

  if ! upgrade_head >/tmp/alembic_upgrade.log 2>&1; then
    if grep -q "Can't locate revision identified by" /tmp/alembic_upgrade.log; then
      echo "Detected stale Alembic revision marker. Resetting alembic_version and retrying..."
      psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 -c "DROP TABLE IF EXISTS alembic_version;"

      if ! has_migration_files; then
        create_initial_migration
      fi

      if ! upgrade_head; then
        echo "Alembic upgrade failed after stale marker reset."
        exit 1
      fi
    elif grep -q "contains null values" /tmp/alembic_upgrade.log; then
      echo "Detected NOT NULL constraint violation. Truncating affected tables and retrying..."
      psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE triage_sessions RESTART IDENTITY CASCADE;"
      psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE chat_sessions RESTART IDENTITY CASCADE;"
      if ! upgrade_head; then
        echo "Alembic upgrade failed after table reset."
        cat /tmp/alembic_upgrade.log
        exit 1
      fi
    else
      echo "Migration failed with unexpected error:"
      cat /tmp/alembic_upgrade.log
      exit 1
    fi
  fi
else
  echo "No Alembic directory found in /app. Skipping migrations."
fi

echo "Starting AI Service..."
exec "$@"
