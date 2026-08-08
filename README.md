# Dolos — The Craftsman of Lies

**Mythic wrapper payload type — encode shellcode on your own infrastructure.**

Dolos takes an existing built payload, transfers it to an external server over SSH, runs your encoder, and returns the result. It does no encoding itself — the remote encoder does all the work.

---

## Features

- **File-based multi-profile config** — each encoder profile has its own SSH server, command, timeout, and bypass profiles
- **Auto-install tools on remote servers** — idempotent install scripts detect and install required tools (Python, etc.) before encoding
- **Bypass profiles** — EDR evasion configs per encoder, shown/hidden automatically in the build UI
- **Shellcode deduplication** — detects duplicate wraps and auto-rebuilds with a fresh UUID
- **Per-profile SSH auth** — password, key, or both — configured per encoder
- **Per-profile timeout, success/fail strings** — all from `encoder_profile.json`, no UI clutter
- **Dynamic timeout dropdown** — shows the selected encoder's timeout, type a custom value to override
- **Full session logging** — timestamped JSON artifact with every SSH/SFTP event
- **Rotating file logs** — DEBUG-level detail at `/tmp/dolos/dolos.log`, CRITICAL-only in `docker logs`
- **Format-agnostic** — magic-byte detection sets the correct file extension

---

## Quick Start

### 1. Configure encoder profiles

Edit `Payload_Type/dolos/configs/encoders/` — each subdirectory has an `encoder_profile.json`:

```json
{
    "index": 1,
    "label": "PyEncoder_v1",
    "enabled": true,
    "command": "py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}",
    "ssh_server": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "operator",
        "password": "",
        "keys": { "enabled": true, "path": "../../ssh_keys/tiny11/id_ed25519" }
    },
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "toolset": "pyencoderv1",
    "bypass_profiles": ""
}
```

Field reference:

| Field | Required | Description |
|-------|----------|-------------|
| `label` | ✅ | Unique name, shown in Mythic dropdown |
| `enabled` | ✅ | `false` = hidden from UI |
| `command` | ✅ | Remote command template with `{workdir}`, `{input}`, `{output}`, `{bypass_profile}` placeholders |
| `ssh_server` | ✅ | SSH connection config (host, port, username, password, keys) |
| `timeout` | ✅ | Seconds before SSH command is killed |
| `success_string` | ✅ | String in stdout confirming success |
| `fail_string` | ✅ | String in stdout/stderr indicating failure |
| `install_tools` | ✅ | `true` = run install script before encoding; `false` = skip |
| `toolset` | ⬜ | Subdirectory name under `configs/tools/` (e.g., `"pyencoderv1"`) |
| `bypass_profiles` | ⬜ | Relative path to bypass profiles directory, or `""` |

### 2. Deploy the encoder on the remote server

Copy `dev_tools/encoder/encoder.py` to `C:\tools\encoder.py` on the remote Windows server. If `install_tools` is `true`, Dolos will attempt to install Python automatically via `winget`.

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

| Param | Type | Description |
|-------|------|-------------|
| Encoder | ChooseOne | Encoder profile from `configs/encoders/` (dynamic dropdown) |
| Bypass Profile | ChooseOne | Shown only for encoders with bypass profiles (dynamic dropdown) |
| Timeout | ChooseOneCustom | Shows the selected encoder's timeout. Type a custom value to override. Permanent changes go in `encoder_profile.json`. |
| Regenerate Shellcode | Boolean | Auto-rebuild if shellcode already wrapped (default: true) |

Success and fail strings come from the encoder profile — they're per-encoder constants, not editable in the UI.

---

## Tool Installation

When `install_tools` is `true` and `toolset` is set, Dolos:

1. Detects the remote OS (Windows or Linux)
2. Uploads all files from `configs/tools/{toolset}/` to the remote workdir
3. Runs the appropriate install script (`install_windows.ps1` or `install_linux.sh`)
4. If the script fails → build fails with a clear error message
5. If the script succeeds → continues with encoding

Scripts are **idempotent** — if tools are already present, they exit 0 immediately. No state tracking needed.

### Tool setup directories

```
configs/tools/
├── pyencoderv1/          ← installs py.exe (Python) on Windows
│   ├── install_windows.ps1
│   ├── install_linux.sh
│   └── (add .py scripts, requirements.txt, etc.)
├── passthrough/           ← same as pyencoderv1
│   ├── install_windows.ps1
│   └── install_linux.sh
├── donutx64/              ← verifies donut.exe exists on Windows
│   ├── install_windows.ps1
│   └── install_linux.sh
└── balliskit/              ← installs Python for ShellcodePack/MacroPack
    ├── install_windows.ps1
    ├── install_linux.sh
    └── SETUP.md
```

**For donut, balliskit, and other encoders**: These directories contain a `SETUP.md` explaining that Dolos operators must supply their own encoder tools or connect to a server where they're already installed. See each directory's `SETUP.md` for details and purchase links.

---

## Config Directory

```
Payload_Type/dolos/configs/
├── encoders/
│   └── pyencoder/            ← sample (placeholder credentials)
│       └── encoder_profile.json
└── ssh_keys/
    └── (add key directories, gitignored)
```

Private keys, passwords, and bypass profiles are **gitignored**. The repo ships only the sample `pyencoder` profile with placeholder credentials. Operators customize on the server.

The live server directory (`dolos_profiles/`, bind-mounted at `/Mythic/configs/`) contains the real profiles:

```
dolos_profiles/
├── encoders/
│   ├── pyencoder/
│   ├── passthrough/
│   ├── donut_x64/
│   └── balliskit/
│       ├── macropack/
│       ├── shellcodepack/
│       └── bypass_profiles/   ← gitignored
├── ssh_keys/                  ← gitignored
└── tools/
    ├── pyencoderv1/
    ├── passthrough/
    ├── donutx64/
    └── balliskit/
```

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
  Detect remote OS
     │
     ▼
  Install tools (if install_tools=true)
     │
     ▼
  Upload payload + supporting files ──▶ Run encoder ──▶ Download result
     │                                                          │
     ▼                                                          ▼
  Validate magic bytes                              Store result + session log
```

---

## Changelog

- **v0.13.0** — Auto-install tools on remote servers. `install_tools` and `toolset` fields in encoder profiles. Idempotent install scripts per OS. Success/fail strings moved from UI to profile JSON. Timeout changed to ChooseOneCustom with dynamic query.
- **v0.12.0** — Removed profile upload UI (scraped). Dynamic timeouts from encoder profiles. Profile upload via backend only.
- **v0.11.0** — File-based multi-profile config. Per-profile SSH, bypass profiles, enabled flag, config hot-reload.
- **v0.10.0** — Shellcode deduplication via Hasura + MythicRPC. Auto-rebuild with fresh UUID.
- **v0.9.2** — Container log rotation. Version from `agent_capabilities.json`.
- **v0.9.0** — SSH key authentication. Regenerate Shellcode build param.
- **v0.5.1** — `resp.payload` lowercase fix (zero-byte payloads).

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