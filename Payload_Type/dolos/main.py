"""Dolos service entry point.

A Mythic wrapper payload type - encoder choices loaded from configs/ directory
(encoder_profile.json files) instead of environment variables.

Config hot-reload: a background thread polls for file changes and signals a
resync coroutine running on mythic_container's event loop. Editing files in
dolos_profiles/ on the host causes the Mythic UI dropdowns to update
without a container restart.

Local debugging:
  Set RABBITMQ_CONFIG=local to use rabbitmq_config.local.json.
  Set DOLOS_DEV_MODE=1 to disable SSL verification for self-signed certs.
  Set DOLOS_CONFIG to the absolute path of the configs/ directory.
"""

import asyncio
import logging
import os
import ssl
import sys
import threading
import time

mythic_container_dir = os.path.dirname(os.path.abspath(__file__))

# ── Local debugging: use a local rabbitmq_config if RABBITMQ_CONFIG=local ──

if os.environ.get("RABBITMQ_CONFIG") == "local":n    local_config = os.path.join(mythic_container_dir, "rabbitmq_config.local.json")
    default_config = os.path.join(mythic_container_dir, "rabbitmq_config.json")
    if os.path.exists(local_config):
        import shutil
        shutil.copy2(local_config, default_config)
        print(f"[DOLOS] Using local RabbitMQ config: {local_config}")
    else:
        print(f"[DOLOS] WARNING: RABBITMQ_CONFIG=local but {local_config} not found")
        print(f"[DOLOS] Running inside Docker - RABBITMQ_* env vars are set by mythic-cli, no config file needed.")
        print(f"[DOLOS] For local dev, create rabbitmq_config.local.json in InstalledServices/dolos/")

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
        if not p.enabled:
            print(f"[DOLOS]   {p.label} [DISABLED]")
            continue
        status = "VALID" if p.valid else f"INVALID: {'; '.join(p.validation_errors)}"
        bypass_info = f", {len(p.bypass_profiles)} bypass profiles" if p.bypass_profiles else ""
        print(f"[DOLOS]   {p.label} [{status}{bypass_info}]")

import mythic_container
import dolos  # noqa: F401 - triggers __init__.py which imports builder.py

logger = logging.getLogger("dolos")

# ── Config watcher: detect file changes and re-sync with Mythic ──
#
# Mythic's React UI does NOT call dynamic_query_function for build parameters.
# Build parameter choices are set once at container sync and cached by the frontend.
#
# Solution: a background thread polls for file changes. When detected, it
# signals a coroutine on mythic's event loop to reload profiles and force a
# Mythic payload type re-sync. This updates dropdown choices without restart.

_CONFIG_CHECK_INTERVAL = 5  # seconds between mtime checks
_pending_resync = threading.Event()


async def _do_resync():
    """Re-read config, update build params, and force Mythic re-sync."""
    from dolos.agent_functions.builder import _update_build_params
    from mythic_container.PayloadBuilder import SendMythicRPCSyncPayloadType

    config_loader._reset_cache()
    profiles = config_loader.load_profiles()
    valid = sum(1 for p in profiles if p.valid)
    logger.critical(
        "[DOLOS-WATCHER] Reloaded %d profile(s): %d valid, %d with errors",
        len(profiles), valid, len(profiles) - valid,
    )
    for p in profiles:
        if not p.enabled:
            logger.critical("[DOLOS-WATCHER]   %s [DISABLED]", p.label)
        elif p.valid:
            bypass_info = f", {len(p.bypass_profiles)} bypass" if p.bypass_profiles else ""
            logger.critical("[DOLOS-WATCHER]   %s [VALID%s]", p.label, bypass_info)
        else:
            logger.critical("[DOLOS-WATCHER]   %s [INVALID: %s]", p.label, "; ".join(p.validation_errors))
    _update_build_params()
    result = await SendMythicRPCSyncPayloadType("dolos", [])
    logger.critical("[DOLOS-WATCHER] Mythic re-sync result: %s", result)


async def _resync_loop():
    """Coroutine on mythic's event loop, checks for resync signals."""
    while True:
        await asyncio.sleep(2)
        if _pending_resync.is_set():
            _pending_resync.clear()
            try:
                await _do_resync()
            except Exception as e:
                logger.exception("[DOLOS-WATCHER] Re-sync failed: %s", e)


def _config_watcher():
    """Background thread: polls for config file changes and signals resync."""
    while True:
        time.sleep(_CONFIG_CHECK_INTERVAL)
        try:
            if config_loader._check_mtimes():
                logger.critical("[DOLOS-WATCHER] Config files changed on disk, scheduling re-sync")
                _pending_resync.set()
        except Exception as e:
            logger.exception("[DOLOS-WATCHER] Error: %s", e)


# Start the config watcher thread
_watcher_thread = threading.Thread(target=_config_watcher, daemon=True, name="dolos-config-watcher")
_watcher_thread.start()
logger.critical("[DOLOS-WATCHER] Config watcher started (checking every %ds)", _CONFIG_CHECK_INTERVAL)

# ── Patch mythic's event loop to include our resync coroutine ──
# mythic's start_and_run_forever creates a new event loop and runs forever.
# We replace it with our own version that also schedules _resync_loop on that loop.

_original_start = mythic_container.mythic_service.start_and_run_forever


def _patched_start():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(mythic_container.mythic_service.start_services())
        # Schedule our resync loop on the same event loop as mythic
        loop.create_task(_resync_loop())
        logger.critical("[DOLOS-WATCHER] Resync loop scheduled on mythic event loop")
        loop.run_forever()
        logger.error("start_and_run_forever finished")
    except KeyboardInterrupt:
        sys.exit(0)
    finally:
        loop.close()


mythic_container.mythic_service.start_and_run_forever = _patched_start
mythic_container.mythic_service.start_and_run_forever()