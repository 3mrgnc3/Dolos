# <img src="Payload_Type/dolos/dolos/dolos.svg" width="56" height="56" alt="Dolos logo"> Dolos - The Craftsman of Lies

**Mythic wrapper payload type — encode shellcode on your own infrastructure.**

Dolos takes an existing built payload, transfers it to an external server over SSH, runs your encoder, and returns the result. It does no encoding itself — the remote encoder does all the work.

---

## Quick Start

### 1. Configure encoder profiles

Edit `Payload_Type/dolos/configs/encoders/` — each subdirectory has an `encoder_profile.json`:

```json
{
    "index": 0,
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

### 2. Deploy the encoder on the remote server

Copy `dev_tools/encoder/encoder.py` to `C:\tools\encoder.py`. Requires Python (`py.exe`) and `csc.exe` (built into Windows). If `install_tools` is `true`, Dolos will attempt to install Python automatically.

### 3. Install into Mythic

```bash
cd /path/to/Mythic
./mythic-cli uninstall dolos
bash /path/to/Dolos/dev_tools/remote/full_uninstall.sh
./mythic-cli install folder ../Dolos
```

### 4. Build

Mythic UI → **Create Wrapper** → select a payload → select Dolos → pick encoder → Build.

Once installed, full documentation is available in the Mythic UI under the Dolos agent docs, including build parameter details, encoder setup guides, and troubleshooting.

---

## Config Directory

```
Payload_Type/dolos/configs/
├── encoders/
│   └── pyencoder/
│       └── encoder_profile.json      ← sample (placeholder credentials)
├── ssh_keys/
│   └── (add your key directories)
└── tools/
    ├── pyencoderv1/                  ← installs Python on remote servers
    │   ├── install_windows.ps1
    │   └── install_linux.sh
    ├── donut_x64/SETUP.md           ← donut.exe is standalone
    ├── balliskit/SETUP.md           ← commercial tools from balliskit.com
    └── passthrough/SETUP.md          ← needs Python
```

Private keys and passwords are **gitignored**. The repo ships a sample `pyencoder` profile only. Operators customize on the server.

---

## Changelog

- **v0.13.0** — Auto-install tools on remote servers. Success/fail strings in profile JSON. ChooseOneCustom timeout.
- **v0.11.0** — File-based multi-profile config. Per-profile SSH, bypass profiles, auto-scaffold.
- **v0.10.0** — Shellcode deduplication via Hasura + MythicRPC. Auto-rebuild with fresh UUID.
- **v0.9.0** — SSH key authentication. `Regenerate Shellcode` build param.
- **v0.5.1** — `resp.payload` lowercase fix.