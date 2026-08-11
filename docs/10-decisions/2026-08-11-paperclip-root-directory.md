# Decision: Configs at /Mythic/ Root — Never in Subdirectories

**Date**: 2026-08-11  
**Status**: Approved — architectural constraint

## Context

The Mythic paperclip UI (Installed Services → Agent → file browser) shows files at the `/Mythic/` root level of the container. It **cannot navigate into subdirectories**. Operators click the paperclip icon and see a flat list of files alongside `Dockerfile`, `main.py`, etc.

## Decision

All Dolos configuration files MUST live at `/Mythic/` root — the same directory as `Dockerfile` and `main.py`. **Never create subdirectories for configs.** The paperclip UI cannot descend into them.

This means:
- `00_Encoder_PyEncoder.json` → `/Mythic/00_Encoder_PyEncoder.json`
- `00_Tool_pyencoder_install.ps1` → `/Mythic/00_Tool_pyencoder_install.ps1`
- `00_Tool_pyencoder_encode.py` → `/Mythic/00_Tool_pyencoder_encode.py`

NOT:
- ❌ `/Mythic/configs/00_Encoder_PyEncoder.json` — invisible to paperclip
- ❌ `/Mythic/encoders/00_Encoder_PyEncoder.json` — invisible to paperclip
- ❌ Any subdirectory — invisible to paperclip

## Rationale

Paperclip is the primary operator interface for editing configs. If configs are in subdirectories, operators cannot see or edit them without SSH access to the host. This defeats the entire purpose of paperclip-editable configs.

## CONSEQUENCE

The flat-file naming convention (`NN_Type_Detail.ext`) exists BECAUSE we can't use directories. The filename IS the metadata — group number, type, and detail are encoded in the filename itself.

## CONSEQUENCE

`CONFIG_DIR` defaults to `/Mythic/` (not `/Mythic/configs/`). The Dockerfile `COPY` commands place files directly at `/Mythic/`. The `docker-compose` section in `config.json` must NOT set `DOLOS_CONFIG` to a subdirectory.