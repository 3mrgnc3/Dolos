#!/usr/bin/env bash
#
# dev_tools/remote/reinstall.sh
#
# Full reinstall cycle for the Dolos container in Mythic.
# Stops the old container, removes it, cleans DB records, reinstalls
# from the current source, and verifies startup.
#
# Usage: bash dev_tools/remote/reinstall.sh
#
set -uo pipefail

MYTHIC_DIR="${MYTHIC_DIR:-/home/mrgnc/MythicC2/Mythic}"
DOLOS_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[DOLOS]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

echo "=== Dolos Container Reinstall ==="
echo ""
echo "Source: $DOLOS_DIR"
echo "Mythic: $MYTHIC_DIR"
echo ""

# ── Step 1: Uninstall ──

info "[1/4] Uninstalling dolos..."
cd "$MYTHIC_DIR" || fail "Mythic dir not found: $MYTHIC_DIR"
./mythic-cli uninstall dolos 2>&1 || warn "mythic-cli uninstall returned non-zero (may be ok)"

# ── Step 2: Clean DB ──

info "[2/4] Cleaning DB records..."
bash "$DOLOS_DIR/dev_tools/remote/full_uninstall.sh" 2>&1 || warn "full_uninstall returned non-zero (may be ok)"

# ── Step 3: Reinstall ──

info "[3/4] Installing from $DOLOS_DIR..."
./mythic-cli install folder "$DOLOS_DIR" 2>&1 || fail "mythic-cli install failed"

# ── Step 4: Verify ──

info "[4/4] Verifying..."
sleep 3

echo ""
echo "Container status:"
docker ps --filter name=dolos --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || warn "docker ps failed"

echo ""
echo "Container logs (last 10 lines):"
docker logs dolos --tail 10 2>&1 || warn "docker logs failed"

echo ""
VERSION=$("$DOLOS_DIR/.venv/bin/python" -c "from mythic_container import containerVersion; print(containerVersion)" 2>/dev/null || echo "unknown")
PVERSION=$("$DOLOS_DIR/.venv/bin/python" -c "import mythic_container; print(mythic_container.PyPi_version)" 2>/dev/null || echo "unknown")
info "Local mythic_container version: $PVERSION"

echo ""
ok "Reinstall complete."
echo ""
echo "Next steps:"
echo "  - Check Mythic UI: https://127.0.0.1:7443"
echo "  - Verify params: Create Wrapper → Dolos"
echo "  - Check logs: docker logs dolos"
echo "  - Check file logs: docker exec dolos cat /tmp/dolos/dolos.log"