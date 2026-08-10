# Decision: Fix infinite resync loop — v1.1.0

**Date**: 2026-08-10
**Status**: Approved and implemented

## Problem

`_check_mtimes()` in `config_loader.py` tracked ALL files under the config tree (9 files: encoder profiles, .gitkeep, SETUP.md, install scripts) but `load_profiles()` only stored mtimes for `encoder_profile.json` files (1 file) in `_profile_mtimes`.

This permanent key-set mismatch meant `_check_mtimes()` always returned `True` → triggered `SendMythicRPCSyncPayloadType` on every 5-second poll → Mythic posted "Successfully synced dolos" ~12 times/minute to the event feed.

## Fix (2 files, 3 changes)

### 1. `config_loader.py` — `_check_mtimes()`: Fixed key-set comparison

`load_profiles()` now stores mtimes for ALL files under the config tree (not just `encoder_profile.json`). This matches what `_check_mtimes()` tracks, eliminating the permanent mismatch.

Also added a guard: if `_profile_mtimes` is empty (first run), always trigger. Otherwise only trigger if keys actually differ or files were modified.

### 2. `main.py` — `_do_resync()`: Added 60-second minimum resync interval

Even if config legitimately changes, don't resync more than once per minute. Prevents rapid-fire syncs during active editing.

### 3. `main.py` — `_CONFIG_CHECK_INTERVAL`: Increased from 5s to 10s

Config edits are operator actions. 10-second detection is plenty.

## Expected result

- 1 sync event on container startup (from Mythic's own `syncPayloadData()`)
- 0 events until an operator edits config files
- When config changes: exactly 1 resync within ~70 seconds max (10s poll + 60s cooldown)