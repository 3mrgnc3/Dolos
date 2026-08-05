#!/usr/bin/env bash
#
# dev_tools/remote/smoke_test.sh
#
# Quick smoke test of the running Dolos container.
# Checks container status, RabbitMQ connection, icon loading, and version.
#
# Usage: bash dev_tools/remote/smoke_test.sh
#
set -uo pipefail

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
fail()  { echo -e "  ${RED}✗${NC} $1"; }
warn()  { echo -e "  ${YELLOW}!${NC} $1"; }

echo "=== Dolos Container Smoke Test ==="
echo ""

# ── 1. Container running ──

echo "[1] Container status"
if docker ps --filter name=dolos --format '{{.Names}}' | grep -q dolos; then
    STATUS=$(docker ps --filter name=dolos --format '{{.Status}}')
    ok "Container is running ($STATUS)"
else
    fail "Container is NOT running"
    echo "  Start it with: bash dev_tools/remote/reinstall.sh"
    exit 1
fi

# ── 2. RabbitMQ connection ──

echo ""
echo "[2] RabbitMQ connection"
if docker logs dolos 2>&1 | grep -q "Successfully connected to rabbitmq"; then
    ok "RabbitMQ connected"
else
    fail "RabbitMQ NOT connected"
    echo "  Last 5 log lines:"
    docker logs dolos --tail 5 2>&1 | sed 's/^/    /'
fi

# ── 3. Icon loading ──

echo ""
echo "[3] Icon loading"
if docker logs dolos 2>&1 | grep -q "failed to read agent icon"; then
    fail "Icon failed to load — FileNotFoundError in logs"
else
    ok "No icon errors in logs"
fi

# ── 4. Version ──

echo ""
echo "[4] Version check"
V=$(docker exec dolos python3 -c "from dolos.agent_functions.builder import Version; print(Version)" 2>/dev/null)
if [ -n "$V" ]; then
    ok "Dolos version: $V"
else
    warn "Could not read version from container"
fi

# ── 5. File logs ──

echo ""
echo "[5] File log rotation"
if docker exec dolos test -f /tmp/dolos/dolos.log 2>/dev/null; then
    SIZE=$(docker exec dolos wc -c < /tmp/dolos/dolos.log 2>/dev/null || echo "unknown")
    ok "Log file exists: /tmp/dolos/dolos.log ($SIZE bytes)"
else
    warn "Log file not found at /tmp/dolos/dolos.log (may not have been triggered yet)"
    echo "  File logs are created on first build. Run a build to generate them."
fi

# ── 6. Mythic sync ──

echo ""
echo "[6] Mythic sync"
SYNC=$(docker logs dolos 2>&1 | grep -c "Successfully synced dolos")
if [ "$SYNC" -ge 1 ]; then
    ok "Synced with Mythic ($SYNC sync events)"
else
    warn "No sync events found in logs"
fi

echo ""
echo "=== Smoke test complete ==="