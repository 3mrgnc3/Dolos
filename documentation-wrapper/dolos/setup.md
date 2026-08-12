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

## How Configuration Works

Dolos uses **flat-file configuration** at the `/Mythic/` root directory. All encoder profiles,
tool scripts, and install scripts are visible and editable via the Mythic **paperclip UI** —
no restart needed after edits.

### v2 Config Directory

Inside the Docker container, configs live at `/Mythic/` root:

```
/Mythic/
├── 00_PyEncoder.json              ← encoder profile (paperclip-editable)
├── 00_Tool_pyencoder_encode.py    ← encoder script (paperclip-editable)
├── 00_Tool_pyencoder_install.ps1  ← install script (paperclip-editable)
├── 01_ShellcodePack.json          ← example: Balliskit encoder profile
├── 01_Tool_shellcodepack_install.ps1  ← example: Balliskit install script
├── main.py
└── dolos/
    └── ...
```

Each encoder is a single JSON file named `NN_<Label>.json` where `NN` is a group number.
Tool files matching the same group number are uploaded before encoding.

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
    "notes": "Windows-only encoder using py.exe"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | int | yes | — | Must be `2`. Identifies the config schema version. |
| `label` | string | yes | — | Display name in Mythic UI dropdown. |
| `enabled` | bool | yes | — | Set `false` to hide from the dropdown without deleting. |
| `command` | string | yes | — | Remote command template. Must contain `{workdir}`, `{input}`, and `{output}` placeholders. |
| `ssh_host` | string | yes | — | Hostname or IP of the remote SSH server. |
| `ssh_port` | int | no | 22 | SSH port. |
| `ssh_username` | string | yes | — | SSH username. |
| `ssh_password` | string | no | `""` | Password for SSH auth. Can be empty when using key auth. |
| `ssh_key_enabled` | bool | no | `false` | Set `true` to authenticate with an SSH key from Mythic User Secrets. |
| `ssh_key_secret` | string | no | — | Name of the Mythic User Secret containing the PEM private key. Convention: `DOLOS_<NN>_ENCODER_SSH_KEY`. |
| `timeout` | int | no | 300 | Command timeout in seconds. Can be overridden per-build via the Timeout parameter. |
| `success_string` | string | no | `ENCODING_SUCCESS` | String in stdout confirming successful encoding. |
| `fail_string` | string | no | `ENCODING_FAILED` | String in stdout/stderr indicating failure. |
| `install_tools` | bool | no | `false` | Whether to upload and run install scripts before encoding. |
| `bypass_refs` | array | no | `[]` | Names of bypass profile files to include (e.g., `["01_Bypass_AMSI"]`). When present, a **Bypass Profile** dropdown appears in the build dialog. |
| `notes` | string | no | — | Operator notes (not used by Dolos, visible in paperclip UI). |

### SSH Authentication

**Password auth**: Set `ssh_password` in the encoder profile JSON. Suitable for development or isolated networks.

**Key auth (recommended for production)**:
1. Set `ssh_key_enabled: true` and `ssh_password: ""`
2. Set `ssh_key_secret` to the Mythic User Secret name (e.g., `DOLOS_00_ENCODER_SSH_KEY`)
3. Add your SSH private key PEM in Mythic UI → Settings → Secrets

The private key is injected at build time via Mythic's secrets API — no key files stored on disk.

### Bypass Profiles

Some encoders (like [Balliskit's ShellcodePack](https://balliskit.com/)) support bypass profiles
for EDR evasion. These are JSON files in `/Mythic/` named `NN_<EncoderName>_<BypassName>.json`.
When an encoder has bypass refs, the **Bypass Profile** dropdown appears in the Mythic build dialog.

The `{bypass_profile}` placeholder in the command template resolves to the selected profile's
stem name (filename without `.json`).

### Adding a New Encoder Profile

1. In the Mythic paperclip UI for the Dolos container, create a new file:
   `01_NewEncoder.json` (group number `01` for a second encoder)
2. Fill in the v2 profile JSON with your SSH server details and command template
3. If the encoder needs install scripts, create `01_Tool_<name>_install.ps1` (or `.sh`)
4. The new encoder appears in the **Encoder** dropdown immediately — no restart needed

To add [Balliskit's ShellcodePack](https://balliskit.com/), see the example in [Encoder Setup](encoder-setup).

### Success/Failure Detection

Dolos checks for success and failure strings in the encoder's stdout. These are configured
per-encoder in the profile JSON:

- **`success_string`** (default: `ENCODING_SUCCESS`) — If found in stdout, encoding is confirmed successful
- **`fail_string`** (default: `ENCODING_FAILED`) — If found in stdout/stderr, encoding is confirmed failed

Your encoder should print one of these to stdout:

```python
# Success:
print("ENCODING_SUCCESS")

# Failure:
print("ENCODING_FAILED: Invalid input format")
```

### Verifying Connectivity

When you create a wrapper, Dolos automatically tests the SSH connection.
The build progress shows:
- ✅ SSH connectivity
- ✅ Key/password authentication
- ✅ SFTP write test (upload + delete a small test file)

If any step fails, you'll see ❌ with an error message and instructions.

### Tool Auto-Installation

When `install_tools` is `true`, Dolos automatically uploads matching tool files and
runs the install script before encoding:

1. Finds all files matching `NN_Tool_*` with the same group number as the encoder
2. Uploads them to the remote workdir via SFTP
3. Runs `NN_Tool_<name>_install.ps1` (Windows) or `NN_Tool_<name>_install.sh` (Linux)
4. If the script fails → build fails with a clear error message

Scripts are **idempotent** — if tools are already present, they should exit 0 immediately.

## Environment Variables

Only infrastructure-level env vars are needed (no Dolos-specific config env vars):

| Variable | Required | Source |
|----------|----------|--------|
| `HASURA_SECRET` | Yes | Set by mythic-cli |
| `HASURA_HOST` | No | Set by mythic-cli |
| `HASURA_PORT` | No | Set by mythic-cli |
| `RABBITMQ_*` | Yes | Set by mythic-cli |

All encoder config is in flat JSON files at `/Mythic/` — no environment variables needed.