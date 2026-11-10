#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Use only the repository's local PostgreSQL and LocalStack endpoints.
set -a
source ./.env.example
set +a

# Keep destructive failure scenarios away from the developer's Compose project and database.
export COMPOSE_PROJECT_NAME="saas-it-$(openssl rand -hex 6)"
export LOCAL_JWT_SECRET="$(openssl rand -hex 32)"
export POS_SHARED_TOKEN="$(openssl rand -hex 32)"
export ACTIVE_BRANDS=brand_a,brand_b,brand_c
export CATALOG_PORT=18081 ORDER_PORT=18082 WORKER_PORT=18083 MOCK_POS_PORT=18084
export POS_URL="http://mock-pos:$MOCK_POS_PORT"
export POS_TIMEOUT_MS=2500 POS_FAIL_FIRST=0 POS_DELAY_MS=0
export SQS_VISIBILITY_TIMEOUT=8 SQS_MAX_RECEIVE_COUNT=3

compose() {
    docker compose -f compose.yaml --env-file .env.example "$@"
}

cleanup() {
    status=$?
    if (( status != 0 )); then
        compose ps -a || true
        compose logs --tail=25 || true
    fi
    compose down --volumes
    exit "$status"
}
trap cleanup EXIT
compose up --build --wait --wait-timeout 120
python3 -m unittest discover -s tests -v
