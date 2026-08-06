# <img src="Payload_Type/dolos/dolos/dolos.svg" width="56" height="56" alt="Dolos logo"> Dolos - The Craftsman of Lies

**Mythic wrapper payload type - encode shellcode on your own infrastructure.**

Dolos takes an existing built payload, transfers it to an external server over SSH, runs your encoder, and returns the result. It does no encoding itself - the remote encoder does all the work.

---

## Features

- **File-based multi-profile config** - each encoder profile has its own SSH server, command, and optional bypass profiles
- **Bypass profiles** - EDR evasion configs per encoder, shown/hidden automatically in the build UI
- **Shellcode deduplication** - detects duplicate wraps and auto-rebuilds with a fresh UUID
- **Per-profile SSH auth** - password, key, or both - configured per encoder, not globally
- **Full session logging** - timestamped JSON artifact with every SSH/SFTP event
- **Rotating file logs** - DEBUG-level detail at `/tmp/dolos/dolos.log`, CRITICAL-only in `docker logs`
- **Format-agnostic** - magic-byte detection sets the correct file extension

---

## Quick Start

### 1. Configure encoder profiles

Edit `Payload_Type/dolos/configs/encoders/` - each subdirectory has an `encoder_profile.json`:

```json
{
    "index": 0,
    "label": "PyEncoder_v1",
    "command": "py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}",
    "ssh_server": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "operator",
        "password": "",
        "keys": { "enabled": true, "path": "../../ssh_keys/tiny11/id_ed25519" }
    },
    "timeout": 300,
    "bypass_profiles": ""
}
```

See [Encoder Setup](documentation-wrapper/dolos/encoder-setup.md) for full schema, key auth, and bypass profiles.

### 2. Deploy the encoder on the remote server

Copy `dev_tools/encoder/encoder.py` to `C:\tools\encoder.py`. Requires Python (`py.exe`) and `csc.exe` (built into Windows).

### 3. Install

```bash
cd /path/to/Mythic
./mythic-cli uninstall dolos
bash /path/to/Dolos/dev_tools/remote/full_uninstall.sh
./mythic-cli install folder ../Dolos
```

### 4. Build

Mythic UI → **Create Wrapper** → select a payload → select Dolos → pick encoder → Build.

---

## Build Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| Encoder | ChooseOne | - | Encoder profile from `configs/encoders/` |
| Bypass Profile | ChooseOne | (None) | Shown only for encoders with bypass profiles |
| Timeout | Number | 0 | Override profile timeout (0 = use profile default) |
| Success String | String | `ENCODING_SUCCESS` | Stdout search string for success |
| Fail String | String | `ENCODING_FAILED` | Stdout/stderr search string for failure |
| Regenerate Shellcode | Boolean | True | Auto-rebuild if shellcode already wrapped |

---

## Config Directory

```
Payload_Type/dolos/configs/
├── encoders/
│   ├── pyencoder/            ← sample (placeholder credentials)
│   ├── pyencoder_live/       ← real profile (password + key auth)
│   ├── passthrough/          ← passthrough encoder
│   ├── donut_x64/            ← Donut shellcode packer
│   └── balliskit/            ← shared server, shared key
│       ├── macropack/         ← MacroPack encoder
│       ├── shellcodepack/     ← ShellcodePack encoder
│       ├── bypass_profiles/   ← EDR evasion configs (JSON)
│       └── id_ed25519         ← SSH private key (gitignored)
└── ssh_keys/
    ├── tiny11/               ← SSH keys for Windows server
    └── ubuntuSVR01/          ← SSH keys for Linux server
```

Private keys and passwords are **gitignored**. The repo ships a sample `pyencoder` profile only. Operators customize on the server.

---

## How It Works

```
Build request
     │
     ▼
Dedup check ──already wrapped?──▶ Regenerate shellcode with new UUID
     │ no                                  │
     ▼                                    ▼
  SSH connect ◀────────────────────────────┘
     │
     ▼
  Upload payload ──▶ Remote encoder ──▶ Download result
     │                                          │
     ▼                                          ▼
  Validate magic bytes              Store result + session log
```

---

## Changelog

- **v0.11.0** - File-based multi-profile config (encoder profiles with per-profile SSH, bypass profiles, auto-scaffold, `lable` typo normalization). Removed all `DOLOS_SSH_*` and `DOLOS_REMOTE_COMMAND` env vars.
- **v0.10.0** - Shellcode deduplication via Hasura + MythicRPC. Auto-rebuild with fresh UUID. Built-in C# cradle encoder (v2.3, CreateThread).
- **v0.9.2** - Container log rotation (RotatingFileHandler). Version from `agent_capabilities.json`.
- **v0.9.0** - SSH key authentication. `Regenerate Shellcode` build param.
- **v0.5.1** - `resp.payload` lowercase fix (zero-byte payloads).

---

## Development

| File | Purpose |
|------|---------|
| `CLAUDE.md` | How to work in this repo |
| `PLAN.md` | Implementation status |
| `DECISIONS.md` | Design decisions log |
| `dolos/config_loader.py` | Profile loading, validation, path resolution |
| `dolos/hasura.py` | Hasura GraphQL client for dedup |
| `dolos/ssh_client.py` | SSH/SFTP client + session logging |
| `dolos/agent_functions/builder.py` | Build pipeline + dedup logic |

**Local debug**: `bash dev_tools/local/debug.sh` or press F5 in VS Code. See `CLAUDE.md`.

No `sudo` needed. Always uninstall before reinstalling.