+++
title = "Setup"
weight = 10
+++

## Installing Dolos

From your Mythic directory:

```bash
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

To reinstall or update:

```bash
sudo ./mythic-cli uninstall dolos
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

## Configuring Encoder Profiles

Dolos v2 uses **flat-file configs** at the `/Mythic/` root directory. This makes
them visible and editable via the Mythic paperclip UI.

Each encoder is a single JSON file named `00_<EncoderName>.json`. The `00_` prefix
groups it as encoder config (future: `01_` for second encoder, etc).

### Encoder Profile Location

Inside the Docker container, configs live at `/Mythic/` root:

```
/Mythic/
├── 00_PyEncoder.json          ← encoder profile (paperclip-editable)
├── 00_Tool_pyencoder_encode.py ← encoder script (paperclip-editable)
├── 00_Tool_pyencoder_install.ps1 ← install script (paperclip-editable)
├── main.py
└── dolos/
    └── ...
```

### Encoder Profile Format (v2)

```json
{
    "version": 2,
    "label": "PyEncoder",
    "enabled": true,
    "command": "py.exe C:\\tools\\dolos\\encoder.py {workdir}\\{input} {workdir}\\{output}",
    "ssh_host": "192.168.1.100",
    "ssh_port": 22,
    "ssh_username": "operator",
    "ssh_password": "",
    "ssh_key_enabled": false,
    "ssh_key_secret": "DOLOS_00_ENCODER_SSH_KEY",
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "bypass_refs": [],
    "notes": "Windows encoder using py.exe"
}
```

### SSH Authentication

**Password auth**: Set `ssh_password` in the profile JSON.

**Key auth (recommended)**: 
1. Set `ssh_key_enabled: true` and `ssh_password: ""`
2. Set `ssh_key_secret` to the Mythic User Secret name (e.g., `DOLOS_00_ENCODER_SSH_KEY`)
3. Add your SSH private key PEM in Mythic UI → Settings → Secrets

The private key is passed directly via Mythic's secrets API — no key files on disk.

### Bypass Profiles

Bypass profiles are referenced by name in `bypass_refs`. Each bypass profile is a
JSON file in `/Mythic/` named `00_<EncoderName>_<BypassProfileName>.json`.

## Deploying the Encoder

Copy `00_Tool_pyencoder_encode.py` to `C:\tools\dolos\encoder.py` on your remote
server. Requires Python (`py.exe`) and `csc.exe` (built into Windows).

If `install_tools` is `true`, Dolos will attempt to install Python automatically
using the matching install script.