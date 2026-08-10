# Dolos v2 Redesign — Plan

## Problem Statement

Dolos v1.0.9-v1.1.0 uses a **mounted volume + directory structure** pattern for configuration:

```
dolos_profiles/                    ← bind-mounted to /Mythic/configs/
├── encoders/
│   └── pyencoder/
│       └── encoder_profile.json   ← SSH credentials, command, settings
├── ssh_keys/
│   └── .gitkeep
└── tools/
    └── ...                        ← install scripts, binaries
```

This has critical problems:

1. **Not editable via the Mythic UI** — The paperclip file browser in Installed Services shows files inside the container's `/Mythic/` directory, but the configs are in a *separate bind mount* (`dolos_profiles/`) that the paperclip doesn't manage. Operators must SSH into the Mythic host to edit JSON files.

2. **Empty on first install** — The volume starts empty, scaffold creates a disabled sample profile, and the operator sees "No valid encoder profiles" until they manually create one.

3. **Directory management complexity** — Bypass profiles, SSH keys, and tools live in separate subdirectories with path resolution logic. Adding an encoder means creating a directory structure, not just a file.

4. **SSH keys in bind-mounted files** — Private keys sit in plaintext on the Mythic host filesystem, not in Mythic's user secrets system.

5. **No UI feedback** — Error messages about malformed configs only appear in container logs. The operator sees "(no profiles configured)" with no indication of *why*.

6. **Files from dev don't exist in production** — Our local dev had `test_encoders/`, `tools/` with real scripts, etc. The Docker image only has sample configs. On install, the volume starts empty.

## Proposed Architecture: Flat File with Naming Convention

### Core Insight

Mythic's Installed Services paperclip UI lets operators **browse, edit, and upload files** inside the container's `/Mythic/` directory. The `InstalledServices/dolos/` folder IS `/Mythic/` inside the container. If we put our config files there (instead of in a separate bind mount), operators can manage them through the Mythic UI.

### File Naming Convention

All configuration files live in `/Mythic/configs/` (inside the Docker image, baked in, AND editable via paperclip):

```
/Mythic/configs/
├── 00_PyEncoder_v1.json              ← encoder profile (enabled by default)
├── 01_MacroPack_v1.9.json            ← encoder profile (placeholder, disabled)
├── 00_PyEncoder_v1_bypass.json        ← bypass profile for encoder 00
├── 00_SSH_PRIVATE_KEY                ← SSH private key (or reference to Mythic secrets)
```

**Rules:**
- **Two-digit prefix (00-99)** — Sort order / group. All files starting with `00_` belong to the first encoder group.
- **Keywords after prefix** — `Encoder`, `Bypass`, `SSH_KEY`, `Tool` — identify file purpose from filename alone.
- **No directories** — Everything is flat. Related files are grouped by number prefix.
- **`.json` extension for profiles** — Encoder and bypass profiles are JSON.
- **No extension for keys** — SSH private keys are raw PEM.

This means you can enumerate all configs by listing `/Mythic/configs/` and parsing filenames. No directory traversal needed. No directory creation needed.

### Encoder Profile Schema (v2)

```json
{
    "version": 2,
    "type": "encoder",
    "label": "PyEncoder v1",
    "enabled": true,
    "command": "python3 /tools/encoder.py {workdir}/{input} {workdir}/{output}",
    "ssh_server": {
        "host": "127.0.0.1",
        "port": 22,
        "username": "operator",
        "password": "",
        "key_ref": "${00_SSH_PRIVATE_KEY}",
        "key_enabled": true
    },
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "toolset": "pyencoderv1",
    "bypass_profiles": ["00_PyEncoder_v1_bypass.json"],
    "notes": "Default encoder using PyEncoder script"
}
```

Key changes from v1:
- `"version": 2` — Schema version for forward compat
- `"type": "encoder"` — Distinguishes encoder profiles from bypass profiles
- `"key_ref"` instead of `"path"` — Supports `${VAR}` syntax for Mythic user secrets
- `"bypass_profiles"` references by **filename** (not directory path)
- Flat file = no directory nesting

### Bypass Profile Schema (v2)

```json
{
    "version": 2,
    "type": "bypass",
    "label": "AMSI Bypass",
    "enabled": true,
    "config": {
        "technique": "amsi_init_failed",
        "target_os": "windows"
    }
}
```

Bypass profiles are just JSON blobs. The encoder references them by filename. The builder reads the bypass JSON and uploads it to the SSH workdir.

### SSH Key Reference: `${VAR}` Syntax for Mythic Secrets

For SSH authentication, Dolos v2 supports two modes:

1. **Inline password** in the profile JSON (current behavior, kept for backward compat)
2. **`${VAR}` reference** to Mythic user secrets — the profile has `key_ref: "${00_SSH_PRIVATE_KEY}"` and Dolos resolves this at build time by querying Hasura's `secret` table

This means:
- Operator stores their SSH key in **Mythic UI → User Settings → Secrets** as `00_SSH_PRIVATE_KEY`
- Profile references it with `${00_SSH_PRIVATE_KEY}`
- Dolos resolves the reference at build time
- The public key must be manually added to the SSH server's `authorized_keys`

### Removing the Bind Mount

Current `docker-compose.yml` entry:
```yaml
volumes:
  - ./dolos_profiles:/Mythic/configs
```

This gets **removed**. Config files are baked into the Docker image at `/Mythic/configs/` and are editable via the paperclip UI. No more separate `dolos_profiles/` directory.

**Wait — there's a problem.** The paperclip edits files in `InstalledServices/dolos/`, which IS `/Mythic/` inside the container. But if configs are baked into the Docker image, editing files via paperclip edits the bind-mounted `InstalledServices/` copy. When the container restarts or is rebuilt, those edits persist because `InstalledServices/` is the persistent copy. **This actually works correctly** — the files baked into the image are the defaults, and paperclip edits persist across restarts because they edit the `InstalledServices/` copy.

However, the Mythic paperclip editor edits the files *inside the container at runtime*. When the container starts, `InstalledServices/dolos/` is bind-mounted to `/Mythic/`. So edits via paperclip directly modify the files on disk in `InstalledServices/dolos/`. This is the correct pattern.

### Config File Hot-Reload

The v1 mtime-watcher concept stays, but simplified:
- Watch `/Mythic/configs/` for changes (single directory, flat files)
- Parse filenames for grouping
- Reload profiles on mtime change
- Send re-sync to Mythic on changes

### Builder Changes

The `builder.py` becomes much simpler:
1. No more directory traversal for bypass profiles
2. No more relative path resolution for SSH keys
3. Reference bypass profiles by filename instead of directory
4. `${VAR}` references resolved via Hasura at build time
5. Tool files still referenced by name but from the same `/Mythic/configs/` flat dir

### Default Files Shipped

The Docker image ships with sensible defaults (not disabled samples):

```
/Mythic/configs/
├── 00_PyEncoder_v1.json          ← Working encoder profile (needs SSH credentials)
└── 00_PyEncoder_v1_bypass.json    ← Example bypass profile
```

Operators just need to:
1. Edit `00_PyEncoder_v1.json` via the paperclip — add SSH host/username
2. Add their SSH key to Mythic User Secrets as `00_SSH_PRIVATE_KEY`
3. Build

### Validation and Error Messages

Better error feedback in the UI:
- If SSH host is empty → clear error: "Configure ssh_server.host in your encoder profile"
- If `${VAR}` reference can't be resolved → "Secret '00_SSH_PRIVATE_KEY' not found in your Mythic User Settings"
- If bypass profile file missing → "Bypass profile '00_PyEncoder_v1_bypass.json' not found in /Mythic/configs/"
- Malformed JSON → "Failed to parse 00_PyEncoder_v1.json: Expecting property name at line 5"

These appear as build errors in the Mythic UI, not buried in container logs.

## Questions / Concerns

### 1. Paperclip accessibility
The paperclip icon in Installed Services → Agent → Dolos lets operators browse and edit files in the container's `/Mythic/` directory. But configs at `/Mythic/configs/` may not be visible in the paperclip file browser. Need to verify: does the paperclip show all files under `/Mythic/`, or only specific directories?

**Answer needed**: Test whether `/Mythic/configs/` files appear in the Mythic paperclip UI.

### 2. Bind mount vs image-baked
If we remove the `dolos_profiles` bind mount, configs live in the Docker image. Paperclip edits modify the `InstalledServices/` copy. But `docker build` or `mythic-cli build` would overwrite edits. We need a way to preserve operator edits across rebuilds.

**Mitigation**: `mythic-cli build` already doesn't overwrite `InstalledServices/` source — it rebuilds the Docker image FROM the source. The InstallServices copy IS the persistent state.

**Wait — actually**: `mythic-cli install github` DOES overwrite InstalledServices. This means a reinstall would clobber paperclip edits. We need to either:
- a) Keep configs in a persistent bind mount (current approach, but with flat file naming), OR
- b) Document that reinstalls overwrite configs and operators should back up, OR
- c) Make Dolos sync configs to/from Hasura agent_storage so they survive reinstalls

Option (c) is the best UX: Dolos stores its active config state in Hasura `agentstorage` (key-value store accessible via Mythic RPC). On startup, it reads from files first, then checks agent_storage for overrides. Paperclip edits to files continue to work, and configs survive reinstalls.

### 3. SSH key management
Mythic's user secrets live in the Hasura `operationagentstorage` table, keyed by `unique_id`. The `${VAR}` syntax would need Hasura queries to resolve at build time. The builder already has a HasuraClient. We need to add a `resolve_secrets()` method that:
1. Scans the profile for `${...}` references
2. Queries agent_storage for each reference
3. Falls back to the literal string if not found

This is clean and follows the Mythic pattern for secret references.

### 4. Numbered file ordering
Using `00_`, `01_` prefixes for sort order is intuitive. But if an operator adds `05_MyEncoder.json` between `00_` and `01_`, they need to not accidentally reuse a number. The UI (paperclip) doesn't enforce uniqueness. We should validate at load time and log warnings for duplicate numbers.

### 5. What about tools?
Tools (encoder scripts like `pyencoderv1`) still need to be deployed to the SSH server. The `install_tools` + `toolset` pattern works. But instead of a directory structure under `configs/tools/`, we could ship tools as flat files in `/Mythic/configs/` with a `Tool_` keyword prefix:
```
/Mythic/configs/
├── 00_Tool_pyencoderv1_linux.sh
├── 00_Tool_pyencoderv1_windows.ps1
├── 00_Encoder_PyEncoder_v1.json
├── 00_Bypass_AMSI_bypass.json
└── 00_SSH_PRIVATE_KEY
```

But this might be messy. Tools aren't really configs — they're executable scripts that get SFTP'd to remote servers. Maybe keep tools in `/Mythic/tools/` (also accessible via paperclip) and keep `/Mythic/configs/` for profiles only.

## Implementation Plan

### Phase 1: Restructure config files (breaking change → v2.0.0)
- [ ] Redesign `config_loader.py` for flat file naming convention
- [ ] Update `encoder_profile.json` schema to v2 (add `version`, `type`, `key_ref`, `bypass_profiles` as filename references)
- [ ] Remove directory traversal logic
- [ ] Add `${VAR}` secret resolution via Hasura
- [ ] Bake default configs into Docker image
- [ ] Remove `dolos_profiles` bind mount from `docker-compose`
- [ ] Ship working defaults (not disabled samples)
- [ ] Add clear error messages for missing/invalid configs

### Phase 2: UI integration
- [ ] Verify paperclip file browser works with `/Mythic/configs/`
- [ ] Add config file hot-reload via mtime watcher (simpler — single dir, flat files)
- [ ] Add validation with descriptive error messages
- [ ] Test config editing via paperclip → build pipeline

### Phase 3: Persistent config storage
- [ ] Add Hasura `agent_storage` sync for configs (read/write)
- [ ] On startup: load from files, merge with agent_storage overrides
- [ ] On config edit via paperclip: detect mtime change → reload → re-sync
- [ ] On reinstall: restore configs from agent_storage

### Phase 4: Documentation and testing
- [ ] Update documentation for the new config format
- [ ] Add Playwright tests for config management
- [ ] Add documentation about SSH key setup with Mythic user secrets
- [ ] Test full flow: install → edit config via paperclip → build payload → verify output

## Branch Strategy

- Create `feature/ui-managed-configs` branch from current `master`
- All v2 work happens on this branch
- Once stable, merge to `master` as v2.0.0
- Keep `v3-stable` branch for v3 compat (current v1.1.0)