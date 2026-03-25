#!/bin/sh
set -eu

ASYNC_DIALECT_REPLACE='s/postgresql+asyncpg/postgresql/'

# Wait for database
echo "Waiting for database..."
until pg_isready -h postgres -p 5432 -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1; do
    echo "Database is unavailable - sleeping"
    sleep 1
done

ensure_database_exists() {
    PSQL_DATABASE_URL=$(echo "$DATABASE_URL" | sed "$ASYNC_DIALECT_REPLACE")
    TARGET_DB=$(echo "$PSQL_DATABASE_URL" | sed -E 's#^.*/([^/?]+).*$#\1#')
    ADMIN_DB_URL=$(echo "$PSQL_DATABASE_URL" | sed -E 's#/([^/?]+)(\?.*)?$#/postgres\2#')

    if [ -z "$TARGET_DB" ] || [ "$TARGET_DB" = "$PSQL_DATABASE_URL" ]; then
        echo "Could not determine target database from DATABASE_URL: $DATABASE_URL"
        exit 1
    fi

    DB_EXISTS=$(psql "$ADMIN_DB_URL" -tAc "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}'" | tr -d '[:space:]')
    if [ "$DB_EXISTS" != "1" ]; then
        echo "Database '${TARGET_DB}' does not exist. Creating..."
        psql "$ADMIN_DB_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${TARGET_DB}\";"
    fi
    return 0
}

ensure_database_exists

ensure_payment_schema() {
    PSQL_DATABASE_URL=$(echo "$DATABASE_URL" | sed "$ASYNC_DIALECT_REPLACE")
    # VNPay URLs can exceed 500 chars; widen column for existing databases.
    psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 -c "ALTER TABLE IF EXISTS payments ALTER COLUMN payment_url TYPE TEXT;" >/dev/null 2>&1 || true
    return 0
}

ensure_payment_schema

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
        if grep -q "Can't locate revision identified by" /tmp/alembic_revision.log; then
            echo "Detected stale Alembic revision marker before initial revision. Resetting alembic_version and retrying..."
            PSQL_DATABASE_URL=$(echo "$DATABASE_URL" | sed "$ASYNC_DIALECT_REPLACE")
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
            PSQL_DATABASE_URL=$(echo "$DATABASE_URL" | sed "$ASYNC_DIALECT_REPLACE")
            psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 -c "DROP TABLE IF EXISTS alembic_version;"

            if ! has_migration_files; then
                create_initial_migration
            fi

            if ! upgrade_head; then
                echo "Alembic upgrade failed after stale marker reset."
                exit 1
            fi
        else
            cat /tmp/alembic_upgrade.log
            exit 1
        fi
    fi
else
    echo "No Alembic directory found in /app. Skipping migrations."
fi

echo "Starting application..."
exec "$@"
