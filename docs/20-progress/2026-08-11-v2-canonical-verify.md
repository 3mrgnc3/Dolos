# 2026-08-11 v2 Canonical Install Verification

## Status: PASS

Clean canonical install from GitHub `feature/ui-managed-configs` branch, pulling `3mrgnc3/mythic-c2-dolos:v2.0.0` from Docker Hub.

## Verification Checklist

- [x] `mythic-cli install github` — clean install, no errors
- [x] Container starts, loads 1 encoder profile
- [x] `CONFIG_DIR` = `/Mythic/` (paperclip root, not `/Mythic/configs/`)
- [x] No `DOLOS_CONFIG` env var in docker-compose
- [x] Encoder config at `/Mythic/00_Encoder_PyEncoder.json` — visible via paperclip
- [x] `ssh_key_secret` = `DOLOS_00_ENCODER_SSH_KEY` (uppercase, group-prefixed)
- [x] Zero sync spam in logs
- [x] RabbitMQ connected

## Changes in this cycle

- Fixed `CONFIG_DIR` default from `/Mythic/configs` → `/Mythic/` (paperclip cannot navigate subdirs)
- Fixed `ssh_key_secret` to uppercase `DOLOS_00_ENCODER_SSH_KEY` (Mythic User Secrets convention)
- Updated `config_loader.py` docstring to reflect `/Mythic/` root
- Docker image `v2.0.0` rebuilt with `--no-cache`, pushed to Docker Hub
- Updated Mythic Guard `sudo-mythic` rule to exclude `docker exec` commands (false positives on container-internal paths)