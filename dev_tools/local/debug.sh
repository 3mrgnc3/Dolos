#!/usr/bin/env bash
#
# dev_tools/local/debug.sh
#
# Run Dolos locally with debug config (RabbitMQ on localhost, SSL bypass).
#
# Prerequisites:
#   1. Copy rabbitmq_config.local.template.json → rabbitmq_config.local.json
#      and fill in the RabbitMQ password from Mythic's .env (RABBITMQ_PASSWORD)
#   2. The .venv must exist at /home/mrgnc/MythicC2/Dolos/.venv
#   3. Edit configs in Payload_Type/dolos/configs/ with your SSH credentials
#
# Usage:
#   bash dev_tools/local/debug.sh              # Run in foreground
#   bash dev_tools/local/debug.sh --check      # Just check prerequisites
#   bash dev_tools/local/debug.sh --logs       # Run and then show last 50 log lines
#
set -uo pipefail

D="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$D/.venv"
RABBITMQ_LOCAL="$D/Payload_Type/dolos/rabbitmq_config.local.json"
RABBITMQ_TEMPLATE="$D/Payload_Type/dolos/rabbitmq_config.local.template.json"
LOG_DIR="/tmp/dolos"
CONFIGS_DIR="$D/Payload_Type/dolos/configs"

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

ACTION="${1:-run}"

# ── Prerequisites check ──

check_prereqs() {
    local ok=1

    if [ ! -d "$VENV" ]; then
        fail "Virtualenv not found at $VENV"
    fi
    ok "Virtualenv found"

    if [ ! -f "$RABBITMQ_LOCAL" ]; then
        warn "rabbitmq_config.local.json not found"
        echo ""
        echo "  Copy the template and fill in the password:"
        echo "    cp $RABBITMQ_TEMPLATE $RABBITMQ_LOCAL"
        echo ""
        echo "  Get the password from Mythic's .env:"
        echo "    grep RABBITMQ_PASSWORD /home/mrgnc/MythicC2/Mythic/.env"
        echo ""
        fail "Create rabbitmq_config.local.json first"
    fi
    ok "rabbitmq_config.local.json found"

    if ! "$VENV/bin/python" -c "import mythic_container" 2>/dev/null; then
        fail "mythic_container not installed in venv. Run: $VENV/bin/pip install mythic_container==0.6.16"
    fi
    ok "mythic_container available"

    if ! "$VENV/bin/python" -c "import paramiko" 2>/dev/null; then
        fail "paramiko not installed in venv. Run: $VENV/bin/pip install paramiko"
    fi
    ok "paramiko available"

    # Check if icon path resolves
    cd "$D/Payload_Type/dolos" || fail "Can't cd to Payload_Type/dolos"
    if [ ! -f "dolos/dolos.svg" ]; then
        warn "dolos/dolos.svg not found relative to Payload_Type/dolos/"
        warn "  The icon will fail to load in local debug. This is cosmetic only."
    else
        ok "Icon file exists at expected path"
    fi

    # Check config directory
    if [ ! -d "$CONFIGS_DIR" ]; then
        warn "configs/ directory not found at $CONFIGS_DIR"
        warn "  Dolos will auto-scaffold a sample config on first run."
    else
        profile_count=$(find "$CONFIGS_DIR/encoders" -name "encoder_profile.json" 2>/dev/null | wc -l)
        if [ "$profile_count" -eq 0 ]; then
            warn "No encoder_profile.json files found in configs/"
            warn "  Dolos will auto-scaffold a sample config on first run."
        else
            ok "Found $profile_count encoder profile(s) in configs/"
        fi
    fi

    cd "$D" || true
    echo ""
    info "All prerequisites met."
}

# ── Run ──

run_debug() {
    mkdir -p "$LOG_DIR"

    # ── Stop Docker container if running (they compete for RabbitMQ) ──
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^dolos$'; then
        warn "Docker container 'dolos' is running - it will compete for RabbitMQ queues!"
        echo ""
        read -p "Stop the Docker container? [Y/n] " -r
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            docker stop dolos
            ok "Docker container stopped"
        else
            fail "Cannot run local debug alongside Docker container. Stop it first: docker stop dolos"
        fi
    fi

    info "Starting Dolos in local debug mode..."
    info "  RABBITMQ_CONFIG=local        (127.0.0.1 RabbitMQ)"
    info "  DOLOS_DEV_MODE=1             (SSL bypass)"
    info "  DOLOS_LOG_DIR=$LOG_DIR       (file logs)"
    info "  DOLOS_CONFIG=$CONFIGS_DIR    (encoder profiles)"
    echo ""
    info "Press Ctrl+C to stop."
    echo ""

    cd "$D/Payload_Type/dolos"

    RABBITMQ_CONFIG=local \
    DOLOS_DEV_MODE=1 \
    DOLOS_LOG_DIR="$LOG_DIR" \
    DOLOS_CONFIG="$CONFIGS_DIR" \
    "$VENV/bin/python" main.py
}

# ── Show logs ──

show_logs() {
    LOG_FILE="$LOG_DIR/dolos.log"
    if [ -f "$LOG_FILE" ]; then
        info "Last 50 lines from $LOG_FILE:"
        echo ""
        tail -50 "$LOG_FILE"
    else
        warn "Log file not found at $LOG_FILE"
        info "Run debug.sh first to generate logs."
    fi
}

# ── Main ──

case "$ACTION" in
    --check|check|-c)
        check_prereqs
        ;;
    --logs|logs|-l)
        show_logs
        ;;
    --stop|stop|-s)
        info "Stopping Dolos debug process..."
        pkill -f "python.*main.py" 2>/dev/null && ok "Stopped" || warn "No Dolos debug process found"
        ;;
    --help|help|-h)
        echo "Usage: bash dev_tools/local/debug.sh [ACTION]"
        echo ""
        echo "Actions:"
        echo "  (default)  Run Dolos in local debug mode"
        echo "  --check     Check prerequisites (venv, config, icon)"
        echo "  --logs      Show last 50 lines from /tmp/dolos/dolos.log"
        echo "  --stop      Stop the running debug process"
        echo "  --help      Show this help"
        ;;
    run|*)
        check_prereqs
        echo ""
        run_debug
        ;;
esac