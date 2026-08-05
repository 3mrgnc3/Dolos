#!/usr/bin/env bash
#
# dev_tools/full_uninstall.sh
#
# Fully remove the Dolos service from Mythic.
#
# Docker containers run Python as root, creating __pycache__ dirs owned by root.
# mythic-cli uninstall can't delete those (permission denied), which blocks the
# whole uninstall and causes an infinite loop on reinstall. We clean them first
# by mounting each parent dir into an alpine container and deleting __pycache__
# from inside — this removes the directory itself, not just its contents.
#
# After that, mythic-cli uninstall handles everything else.
#
# No sudo required.
#
# Usage:   dev_tools/full_uninstall.sh
#          MYTHIC_DIR=/path/to/Mythic dev_tools/full_uninstall.sh
set -uo pipefail

MYTHIC_DIR="${MYTHIC_DIR:-/home/mrgnc/MythicC2/Mythic}"
PATTERN="dolos"

cd "$MYTHIC_DIR" || { echo "[-] Mythic dir not found: $MYTHIC_DIR"; exit 1; }

echo "[*] Cleaning root-owned __pycache__ dirs..."
for d in InstalledServices/${PATTERN}*; do
    [ -d "$d" ] || continue
    for cachedir in $(find "$d" -name "__pycache__" -type d 2>/dev/null); do
        parent=$(dirname "$cachedir")
        echo "    - $cachedir"
        docker run --rm -v "$(pwd)/$parent:/parentdir" alpine rm -rf /parentdir/__pycache__ 2>/dev/null || true
    done
done

echo "[*] Uninstalling ${PATTERN}* via mythic-cli..."
for d in InstalledServices/${PATTERN}*; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    ./mythic-cli uninstall "$name"
done

echo "[+] Done."