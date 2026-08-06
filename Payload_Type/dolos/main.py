"""Dolos service entry point.

A Mythic wrapper payload type - encoder choices loaded from configs/ directory
(encoder_profile.json files) instead of environment variables.

Local debugging:
  Set RABBITMQ_CONFIG=local to use rabbitmq_config.local.json (for
  connecting to Mythic from your dev machine instead of from Docker).
  Set DOLOS_DEV_MODE=1 to disable SSL verification for self-signed certs.
  Set DOLOS_CONFIG to the absolute path of the configs/ directory for local debug.
"""

import json
import os
import ssl

mythic_container_dir = os.path.dirname(os.path.abspath(__file__))

# ── Local debugging: swap rabbitmq_config.json if RABBITMQ_CONFIG=local ──

if os.environ.get("RABBITMQ_CONFIG") == "local":
    local_config = os.path.join(mythic_container_dir, "rabbitmq_config.local.json")
    default_config = os.path.join(mythic_container_dir, "rabbitmq_config.json")
    if os.path.exists(local_config):
        import shutil
        shutil.copy2(local_config, default_config)
        print(f"[DOLOS] Using local RabbitMQ config: {local_config}")
    else:
        print(f"[DOLOS] WARNING: RABBITMQ_CONFIG=local but {local_config} not found")
        print(f"[DOLOS] Copy rabbitmq_config.local.template.json to rabbitmq_config.local.json and fill in credentials.")

# ── Development mode: disable SSL verification for self-signed certs ──

if os.environ.get("DOLOS_DEV_MODE") == "1":
    ssl._create_default_https_context = ssl._create_unverified_context
    print("[DOLOS] DEV MODE: SSL verification disabled (self-signed certs allowed)")

# ── Load and validate encoder profiles before starting ──

from dolos import config_loader

# Auto-scaffold sample config if needed
config_loader.scaffold_if_needed()

# Load and log profile summary
profiles = config_loader.load_profiles()
valid_count = sum(1 for p in profiles if p.valid)
invalid_count = len(profiles) - valid_count

if valid_count == 0:
    print(f"[DOLOS] WARNING: No valid encoder profiles found. Builds will fail until config is fixed.")
    print(f"[DOLOS] Edit configs in: {config_loader.CONFIG_DIR}")
else:
    print(f"[DOLOS] Loaded {len(profiles)} encoder profile(s): {valid_count} valid, {invalid_count} with errors")
    for p in profiles:
        status = "VALID" if p.valid else f"INVALID: {'; '.join(p.validation_errors)}"
        bypass_info = f", {len(p.bypass_profiles)} bypass profiles" if p.bypass_profiles else ""
        print(f"[DOLOS]   {p.label} [{status}{bypass_info}]")

import mythic_container
import dolos  # noqa: F401 - triggers __init__.py which imports builder.py

mythic_container.mythic_service.start_and_run_forever()