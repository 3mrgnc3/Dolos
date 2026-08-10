"""Dolos v2 service entry point.

Flat-file config in /Mythic/configs/ (paperclip-editable).
SSH keys via Mythic User Secrets (self.secrets).
No scaffolding, no sample configs, no directory traversal.

Config hot-reload: background thread polls mtime, signals resync
coroutine on mythic's event loop. Editing files via paperclip
causes dropdowns to update without container restart.

Local debugging:
  RABBITMQ_CONFIG=local — use rabbitmq_config.local.json
  DOLOS_DEV_MODE=1 — disable SSL verification
  DOLOS_CONFIG=/path/to/configs — override config directory
"""

import asyncio
import logging
import os
import ssl
import sys
import threading
import time

mythic_container_dir = os.path.dirname(os.path.abspath(__file__))

# ── Local debugging ──
if os.environ.get("RABBITMQ_CONFIG") == "local":
    local_config = os.path.join(mythic_container_dir, "rabbitmq_config.local.json")
    default_config = os.path.join(mythic_container_dir, "rabbitmq_config.json")
    if os.path.exists(local_config):
        import shutil
        shutil.copy2(local_config, default_config)
        print(f"[DOLOS] Using local RabbitMQ config: {local_config}")
    else:
        print(f"[DOLOS] WARNING: RABBITMQ_CONFIG=local but {local_config} not found")

if os.environ.get("DOLOS_DEV_MODE") == "1":
    ssl._create_default_https_context = ssl._create_unverified_context
    print("[DOLOS] DEV MODE: SSL verification disabled")

# ── Load encoder profiles before starting ──
from dolos import config_loader

profiles = config_loader.load_profiles()
valid_count = sum(1 for p in profiles if p.valid)

if valid_count == 0:
    print(f"[DOLOS] WARNING: No valid encoder profiles. Create NN_Encoder_*.json files in {config_loader.CONFIG_DIR}")
else:
    print(f"[DOLOS] Loaded {len(profiles)} encoder profile(s): {valid_count} valid")

import mythic_container
import dolos  # noqa: F401 - triggers __init__.py which imports builder.py

logger = logging.getLogger("dolos")

# ── Config watcher ──
_CONFIG_CHECK_INTERVAL = 10
_MIN_RESYNC_INTERVAL = 60
_last_resync_time: float = 0.0
_pending_resync = threading.Event()


async def _do_resync():
    global _last_resync_time
    now = time.monotonic()
    elapsed = now - _last_resync_time
    if _last_resync_time > 0 and elapsed < _MIN_RESYNC_INTERVAL:
        logger.info("[DOLOS-WATCHER] Skipping resync — only %.0fs since last", elapsed)
        return

    from dolos.agent_functions.builder import _update_build_params
    from mythic_container.PayloadBuilder import SendMythicRPCSyncPayloadType

    config_loader._reset_cache()
    profiles = config_loader.load_profiles()
    valid = sum(1 for p in profiles if p.valid)
    logger.critical("[DOLOS-WATCHER] Reloaded %d profile(s): %d valid", len(profiles), valid)
    for p in profiles:
        state = "ENABLED" if p.enabled else "DISABLED"
        status = "VALID" if p.valid else f"INVALID: {'; '.join(p.validation_errors)}"
        bypass_info = f", {len(p.bypass_profiles)} bypass" if p.bypass_profiles else ""
        logger.critical("[DOLOS-WATCHER]   %s [%s %s%s]", p.label, state, status, bypass_info)

    _update_build_params()
    result = await SendMythicRPCSyncPayloadType("dolos", [])
    _last_resync_time = time.monotonic()
    logger.critical("[DOLOS-WATCHER] Mythic re-sync result: %s", result)


async def _resync_loop():
    while True:
        await asyncio.sleep(2)
        if _pending_resync.is_set():
            _pending_resync.clear()
            try:
                await _do_resync()
            except Exception as e:
                logger.exception("[DOLOS-WATCHER] Re-sync failed: %s", e)


def _config_watcher():
    while True:
        time.sleep(_CONFIG_CHECK_INTERVAL)
        try:
            if config_loader._check_mtimes():
                logger.critical("[DOLOS-WATCHER] Config files changed, scheduling re-sync")
                _pending_resync.set()
        except Exception as e:
            logger.exception("[DOLOS-WATCHER] Error: %s", e)


_watcher_thread = threading.Thread(target=_config_watcher, daemon=True, name="dolos-config-watcher")
_watcher_thread.start()
logger.critical("[DOLOS-WATCHER] Config watcher started (checking every %ds)", _CONFIG_CHECK_INTERVAL)

_original_start = mythic_container.mythic_service.start_and_run_forever


def _patched_start():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(mythic_container.mythic_service.start_services())
        loop.create_task(_resync_loop())
        logger.critical("[DOLOS-WATCHER] Resync loop scheduled on mythic event loop")
        loop.run_forever()
    except KeyboardInterrupt:
        sys.exit(0)
    finally:
        loop.close()


mythic_container.mythic_service.start_and_run_forever = _patched_start
mythic_container.mythic_service.start_and_run_forever()