<div align="center">

<img src="Payload_Type/dolos/dolos/dolos.svg" width="48" height="48" alt="Dolos logo">

# Dolos

**Mythic wrapper payload type — encode shellcode on your own infrastructure**

</div>

Dolos takes an existing built payload (Apollo, Merlin, etc.) and wraps it through an external SSH server that runs your encoder. The encoded result comes back to Mythic. **It does no encoding itself** — all processing happens on hardware you control.

The wrapped payload's C2 is already embedded. No C2 profile selection needed — just pick your shellcode, pick your encoder, and build.

---

## Features

- **Multi-encoder support** — configure multiple encoder profiles in `.env` and select from a dropdown at build time. Run different encoders on different servers. Each profile can target a completely different build environment.
- **Shellcode deduplication** — if the same shellcode is selected twice, Dolos detects it and automatically rebuilds the inner payload with the same config but a fresh UUID. Each callback gets unique provenance. Toggle via the "Regenerate Shellcode" build param.
- **Full session logging** — every SSH/SFTP operation is captured in a timestamped JSON artifact. Download from the payload's build page.
- **Format-agnostic** — the remote encoder determines output format. Dolos detects it via magic bytes and sets the correct file extension automatically.
- **Rotating file logs** — container logs go to `/tmp/dolos/dolos.log` with size-based rotation. Nothing lost, no unbounded disk growth.

---

## Quick Start

### 1. Configure SSH and encoder in `.env`

```bash
DOLOS_SSH_HOST=172.28.0.3
DOLOS_SSH_PORT=22
DOLOS_SSH_USERNAME=mrgnc
DOLOS_SSH_PASSWORD=your_password          # password auth (fallback)
# DOLOS_SSH_PRIVATE_KEY=                 # optional: inline PEM for key auth
DOLOS_REMOTE_COMMAND={"PyEncoder_v1.0":"py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}","Donut_x64":"C:\\tools\\donut.exe -i {workdir}\\{input} -o {workdir}\\{output}"}
```

Each key in `DOLOS_REMOTE_COMMAND` appears as an encoder choice in the build form. Add as many profiles as you need — each one can target a different server or encoder binary.

### 2. Deploy the encoder

Copy `dev_tools/encoder/encoder.py` to `C:\tools\encoder.py` on your Windows server. Requires Python (`py.exe`) and `csc.exe` (built into Windows).

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
| Encoder | ChooseOne | — | Encoder command to run (static choices from `DOLOS_REMOTE_COMMAND`) |
| Timeout | Number | 300 | Remote command timeout in seconds |
| Success String | String | `ENCODING_SUCCESS` | Stdout search string for success |
| Fail String | String | `ENCODING_FAILED` | Stdout/stderr search string for failure |
| **Regenerate Shellcode** | **Boolean** | **True** | **When the selected shellcode already has a Dolos build, automatically rebuild it with a fresh UUID. Turn OFF to wrap the same shellcode again without rebuilding.** |

---

## Multi-Profile Architecture

Dolos is designed for teams that run multiple encoders across different build environments. A single Dolos instance can connect to different SSH servers or run different encoder binaries depending on the profile selected at build time.

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Mythic    │────▶│  SSH Server #1   │────▶│  PyEncoder v1.0  │  (C# cradle)
│   (Dolos)   │     │  172.28.0.3      │     │  csc.exe + res   │
│             │     └──────────────────┘     └──────────────────┘
│             │
│  Encoder     │     ┌──────────────────┐     ┌──────────────────┐
│  dropdown    │────▶│  SSH Server #2   │────▶│  Donut x64       │  (shellcode)
│              │     │  10.0.0.5        │     │  donut.exe        │
└─────────────┘     └──────────────────┘     └──────────────────┘
```

Coming soon: multiple hostnames and IP addresses per profile, so the same encoder name can resolve to different servers for redundancy or targeting.

---

## Shellcode Deduplication

When you select the same shellcode for a second Dolos build, Dolos detects that it's already been wrapped and **automatically rebuilds the inner payload** with the same configuration but a fresh UUID. This ensures each wrapped binary has unique provenance — separate callbacks, separate encryption keys, separate tracking.

The "Regenerate Shellcode" toggle (default ON) controls this:
- **ON** (default): Detects duplicate, rebuilds inner payload, wraps the fresh copy
- **OFF**: Detects duplicate, proceeds with the same shellcode anyway — no rebuild, no failure

Build info (encoder output, sizes, timing) is always visible in the payload's **Build Message** and **StdOut** fields, plus the downloadable session log JSON.

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

## Documentation

Full docs at `/docs/wrappers/dolos` in Mythic after install:

- **Setup** — SSH config, env vars, encoder deployment
- **Build Parameters** — all params with descriptions
- **Placeholder Reference** — `{workdir}`, `{input}`, `{output}`, `{file1}`
- **Encoder Setup** — C# cradle encoder, adding custom encoders
- **Troubleshooting** — common errors and fixes

## Development

| File | Purpose |
|------|---------|
| `CLAUDE.md` | How to work in this repo |
| `PLAN.md` | Active implementation plan |
| `DECISIONS.md` | Design decisions log |
| `dolos/hasura.py` | Hasura GraphQL client for dedup and TaskID lookup |
| `dolos/ssh_client.py` | SSH/SFTP client + session logging |
| `dolos/agent_functions/builder.py` | Main build pipeline and dedup logic |

**Local debug**: Run `bash dev_tools/local/debug.sh` or press F5 in VS Code. See `CLAUDE.md` for details.

No `sudo` needed. Always uninstall before reinstalling.