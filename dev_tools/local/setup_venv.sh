#!/usr/bin/env bash
#
# dev_tools/local/setup_venv.sh
#
# Set up or update the Python virtual environment for local debugging.
# Installs mythic_container and paramiko at the correct versions.
#
# Usage: bash dev_tools/local/setup_venv.sh
#
set -uo pipefail

D="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$D/.venv"

echo "=== Dolos Local Debug Environment Setup ==="
echo ""

if [ ! -d "$VENV" ]; then
    echo "[1] Creating virtual environment at $VENV..."
    python3 -m venv "$VENV"
else
    echo "[1] Virtual environment already exists at $VENV"
fi

echo ""
echo "[2] Installing dependencies..."
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install mythic_container==0.6.16 paramiko==5.0.0

echo ""
echo "[3] Verifying imports..."
"$VENV/bin/python" -c "
import mythic_container
import paramiko
print(f'  mythic_container: {mythic_container.PyPi_version}')
print(f'  paramiko: {paramiko.__version__}')
print('  All imports OK')
"

echo ""
echo "[4] Setting up RabbitMQ local config..."
TEMPLATE="$D/Payload_Type/dolos/rabbitmq_config.local.template.json"
LOCAL="$D/Payload_Type/dolos/rabbitmq_config.local.json"

if [ -f "$LOCAL" ]; then
    echo "  rabbitmq_config.local.json already exists"
else
    cp "$TEMPLATE" "$LOCAL"
    echo "  Created rabbitmq_config.local.json from template"
    echo ""
    echo "  *** ACTION REQUIRED ***"
    echo "  Edit $LOCAL and set the RabbitMQ password."
    echo "  Get it from: grep RABBITMQ_PASSWORD /home/mrgnc/MythicC2/Mythic/.env"
    echo ""
fi

echo "=== Setup complete ==="
echo ""
echo "To start debugging:"
echo "  bash dev_tools/local/debug.sh"
echo ""
echo "To check prerequisites:"
echo "  bash dev_tools/local/debug.sh --check"