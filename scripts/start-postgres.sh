#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="klaus-postgres"
IMAGE_NAME="klaus-postgres:latest"
CONTAINERFILE="Containerfile.postgres"
PG_PORT="${PG_PORT:-5432}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }

cd "$(dirname "$0")/.."

# ── 1. Check if the container is already running ──────────────
if podman ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    if podman exec "$CONTAINER_NAME" pg_isready -U klaus -q 2>/dev/null; then
        info "PostgreSQL is already running and accepting connections on port ${PG_PORT}"
        exit 0
    else
        warn "Container exists but PostgreSQL is not ready — restarting..."
        podman restart "$CONTAINER_NAME" >/dev/null
    fi
# ── 2. Check if the container exists but is stopped ──────────
elif podman ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    warn "Container exists but is stopped — starting..."
    podman start "$CONTAINER_NAME" >/dev/null
# ── 3. Build and create the container from scratch ───────────
else
    if ! podman image exists "$IMAGE_NAME" 2>/dev/null; then
        info "Building PostgreSQL + pgvector image..."
        podman build -f "$CONTAINERFILE" -t "$IMAGE_NAME" .
    fi

    info "Creating container ${CONTAINER_NAME}..."
    podman run -d \
        --name "$CONTAINER_NAME" \
        -p "${PG_PORT}:5432" \
        -v klaus_pgdata:/var/lib/postgresql/data \
        "$IMAGE_NAME"
fi

# ── 4. Wait for PostgreSQL to become ready ────────────────────
info "Waiting for PostgreSQL to accept connections..."
for i in $(seq 1 30); do
    if podman exec "$CONTAINER_NAME" pg_isready -U klaus -q 2>/dev/null; then
        info "PostgreSQL is ready on port ${PG_PORT}"
        echo ""
        echo "  Connection URL: postgresql://klaus:klaus@localhost:${PG_PORT}/klaus"
        echo ""
        exit 0
    fi
    sleep 1
done

error "PostgreSQL did not become ready within 30 seconds"
podman logs --tail 20 "$CONTAINER_NAME"
exit 1
