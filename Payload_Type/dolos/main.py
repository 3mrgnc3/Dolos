"""Dolos service entry point.

A Mythic wrapper payload type — no dynamic query monkey-patch needed
(encoder choices are loaded from DOLOS_REMOTE_COMMAND at import time).

Local debugging:
  Set RABBITMQ_CONFIG=local to use rabbitmq_config.local.json (for
  connecting to Mythic from your dev machine instead of from Docker).
  Set DOLOS_DEV_MODE=1 to disable SSL verification for self-signed certs.
"""

import json
import os
import ssl

mythic_container_dir = os.path.dirname(os.path.abspath(__file__))

# ── Local debugging: swap rabbitmq_config.json if RABBITMQ_CONFIG=local ──
# When running inside Docker, rabbitmq_config.json has Docker hostnames
# (mythic_rabbitmq, mythic_server) and no password (RabbitMQ handles auth
# via the Docker network). For local debugging, rabbitmq_config.local.json
# has 127.0.0.1 hostnames and the actual RabbitMQ password.
#
# Usage: RABBITMQ_CONFIG=local python3 main.py
# Or via VS Code: the launch.json sets RABBITMQ_CONFIG=local automatically.

if os.environ.get("RABBITMQ_CONFIG") == "local":
    local_config = os.path.join(mythic_container_dir, "rabbitmq_config.local.json")
    default_config = os.path.join(mythic_container_dir, "rabbitmq_config.json")
    if os.path.exists(local_config):
        # Copy local config over the default one so mythic_container picks it up
        import shutil
        shutil.copy2(local_config, default_config)
        print(f"[DOLOS] Using local RabbitMQ config: {local_config}")
    else:
        print(f"[DOLOS] WARNING: RABBITMQ_CONFIG=local but {local_config} not found")
        print(f"[DOLOS] Copy rabbitmq_config.local.template.json to rabbitmq_config.local.json and fill in credentials.")

# ── Development mode: disable SSL verification for self-signed certs ──
# When DOLOS_DEV_MODE=1, disable SSL verification globally so that
# MythicRPC calls to the local Mythic server work with self-signed certs.
#
# This is ONLY for development. In production (Docker), MythicRPC uses
# RabbitMQ (no HTTPS), so this has no effect.

if os.environ.get("DOLOS_DEV_MODE") == "1":
    ssl._create_default_https_context = ssl._create_unverified_context
    print("[DOLOS] DEV MODE: SSL verification disabled (self-signed certs allowed)")

import mythic_container

# Importing dolos triggers __init__.py -> auto-imports builder.py
# (only builder.py remains — wrappers have no callback commands).
import dolos  # noqa: F401

mythic_container.mythic_service.start_and_run_forever()