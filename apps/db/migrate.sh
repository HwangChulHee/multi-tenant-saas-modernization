#!/bin/sh
set -eu
export PGPASSWORD="$POSTGRES_PASSWORD"
for brand in brand_a brand_b brand_c; do
    prefix=$(printf '%s' "$brand" | tr '[:lower:]' '[:upper:]')
    export CATALOG_PASSWORD=$(printenv "CATALOG_${prefix}_PASSWORD")
    export ORDER_PASSWORD=$(printenv "ORDER_${prefix}_PASSWORD")
    export WORKER_PASSWORD=$(printenv "WORKER_${prefix}_PASSWORD")
    : "${CATALOG_PASSWORD:?}" "${ORDER_PASSWORD:?}" "${WORKER_PASSWORD:?}"
    psql -X -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -v brand="$brand" -v catalog="${brand}_catalog" -v orders="${brand}_order" \
        -v worker="${brand}_worker" -f /migrations/migrate.sql
done
: "${POS_DB_PASSWORD:?}"
psql -X -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /migrations/migrate-pos.sql
