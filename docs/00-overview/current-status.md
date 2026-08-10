# Current Status

**Last updated**: 2026-08-10

## What happened today

1. Investigated GitHub issue #1: "Excessive sync event messages in event feed"
2. Reproduced the bug: ~12 "Successfully synced dolos" messages per minute in Mythic event feed
3. Root-caused: `_check_mtimes()` in `config_loader.py` tracked 9 files, but `load_profiles()` only stored 1 file's mtime in `_profile_mtimes`. Permanent key-set mismatch triggered resync on every 5-second poll cycle.
4. Fixed the bug in two files (`config_loader.py` and `main.py`), committed and pushed as v1.1.0
5. Tore down entire Mythic stack, removed all containers/images, rebuilt fresh
6. About to install Dolos v1.1.0 (not yet built as Docker image) and verify the fix

## Next steps

- Build Dolos v1.1.0 Docker image and install into fresh Mythic
- Run 2-minute event feed test to verify sync spam is gone
- Create `v3-stable` branch from working state
- Create `v4-port` branch from `v3-stable` for Mythic v4 migration
- Build Mythic dev extension for pi (not yet started)