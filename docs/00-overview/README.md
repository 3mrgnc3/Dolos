# Dolos — "The Craftsman of Lies"

Mythic wrapper payload type. Wraps an existing payload, transfers to an external server over SSH/SFTP, runs an encoder, returns the result.

## Current Status

- **Version**: 1.1.0 (bug fix release)
- **Mythic Compatibility**: v3 (MythicContainer Python SDK via `mythic_container` PyPi package)
- **Container Image**: `3mrgnc3/mythic-c2-dolos:v1.0.5` (last published; v1.1.0 not yet built/pushed)
- **Branching Strategy**: 
  - `master` — current working branch, v3 compatible
  - `v3-stable` — to be created from current `master` as a known-working v3 base
  - `v4-port` — to be branched from `v3-stable`, ported to MythicContainer/MythicContainerPyPi SDK

## Key Files

- `Payload_Type/dolos/main.py` — Entry point, config watcher, resync loop
- `Payload_Type/dolos/dolos/config_loader.py` — Encoder profile loading, mtime tracking
- `Payload_Type/dolos/dolos/agent_functions/builder.py` — Build pipeline
- `Payload_Type/dolos/dolos/agent_capabilities.json` — Version and capabilities manifest

## Known Issues

See [30-gotchas/](30-gotchas/) for discovered bugs and fixes.