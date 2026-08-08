#!/bin/bash
# PyEncoder Linux Tool Installation
# Idempotent: safe to run multiple times.
# Checks for python3 and installs via apt if missing.

set -e

# Check if python3 is already available
if command -v python3 &>/dev/null; then
    echo "TOOLS_OK: python3 already available ($(python3 --version 2>&1))"
    exit 0
fi

# Try apt (Debian/Ubuntu)
if command -v apt-get &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq python3
    echo "TOOLS_OK: Python installed via apt"
    exit 0
fi

# Try yum (RHEL/CentOS)
if command -v yum &>/dev/null; then
    yum install -y python3
    echo "TOOLS_OK: Python installed via yum"
    exit 0
fi

echo "TOOLS_INSTALL_FAILED: Could not install python3. No supported package manager found."
exit 1
