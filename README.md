# <img src="3mrgnc3_stricker_v2.png" width="120" height="120" alt="3mrgnc3 Sticker"></br> Dolos - The Craftsman of Lies

**Mythic wrapper payload type — encode shellcode on your own remote infrastructure with traditional scripting and tools.**

Dolos takes an existing built payload, transfers it to an external server over SSH, runs your encoder, and returns the result.

---

## Screenshots

<table>
<tr>
<td width="50%"><img src="assets/screenshots/create_wrapper_dolos_selected.png" alt="Create Wrapper - Dolos Selected"><br><em>Create Wrapper with Dolos selected</em></td>
<td width="50%"><img src="assets/screenshots/step2_build_params.png" alt="Build Parameters"><br><em>Build parameters — Encoder, Bypass, Timeout</em></td>
</tr>
<tr>
<td width="50%"><img src="assets/screenshots/encoder_selected_pyencoder.png" alt="Encoder Selected"><br><em>Encoder dropdown with PyEncoder selected</em></td>
<td width="50%"><img src="assets/screenshots/installed_services_dolos.png" alt="Installed Services"><br><em>Dolos in Installed Services</em></td>
</tr>
<tr>
<td width="50%"><img src="assets/screenshots/docs_index_final.png" alt="Documentation"><br><em>In-app documentation (Hugo)</em></td>
<td width="50%"><img src="assets/screenshots/docs_setup_final.png" alt="Setup Docs"><br><em>Setup documentation</em></td>
</tr>
</table>

---

## Quick Start

### 1. Install into Mythic

```bash
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

This pulls the pre-built Docker image from Docker Hub (`3mrgnc3/mythic-c2-dolos:latest`). No local build required.

To reinstall or update:

```bash
sudo ./mythic-cli uninstall dolos
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

### 2. Configure Encoder Profiles

Edit the `00_*.json` files inside the Dolos container via the **Mythic paperclip UI**:

1. In Mythic UI, go to **Installed Services** → find Dolos → click the **paperclip icon**
2. Edit `00_Encoder_PyEncoder.json` — set your SSH server details
3. Changes take effect immediately (no container restart needed)

### 3. Add SSH Credentials

For key-based auth (recommended):

1. In Mythic UI → **User Settings** → **Secrets**
2. Add your SSH private key PEM as `DOLOS_00_ENCODER_SSH_KEY`
3. In the encoder profile, set `ssh_key_enabled: true` and `ssh_password: ""`

For password auth (development only), set `ssh_password` directly in the profile.

### 4. Build a Wrapper

1. **First**: Build a payload using another payload type (e.g., Apollo, Merlin)
2. Then go to **Create Wrapper** in Mythic UI
3. Select **Dolos** as the wrapper type
4. Choose your encoder profile (e.g., PyEncoder)
5. Select the payload you built in step 1
6. Click **Build**

Dolos will SSH to your encoder server, upload the payload, run the encoder command, and return the result.

---

## User Guide

### How Wrappers Work in Mythic

Dolos is a **wrapper payload type** — it doesn't generate payloads from scratch. Instead, it takes an existing built payload and transforms it through an external encoder. This is why it appears under **Create Wrapper** (not Create Payload).

The workflow is:

1. Build a **base payload** using any payload type (e.g., Apollo for Windows, Poseidon for Linux)
2. Go to **Create Wrapper** → select **Dolos**
3. Choose an encoder profile and the base payload
4. Dolos transfers the base payload to your remote server, runs the encoder, and returns the result

The output format depends on the encoder. It could be an EXE, DLL, shellcode binary, or anything your encoder produces.

### Selecting Different Payloads

When creating a Dolos wrapper, you'll select an inner (base) payload. The **Os** dropdown shows which operating systems the inner payload supports. Since Dolos connects over SSH to a remote server, it lists `SSH Server + Any OS` — the encoder server handles the actual encoding.

**Steps to create a wrapper**:

1. **Create Wrapper** from the Mythic sidebar
2. **Step 1**: Select operating system — `SSH Server + Any OS` is the only option (Dolos uses SSH to a remote server)
3. **Step 2**: Configure build parameters:
   - **Encoder** — Select which encoder profile to use (dropdown from `00_*.json` files)
   - **Bypass Profile** — Select a bypass profile if the encoder has bypass refs (or "(None)")
   - **Timeout** — How long to wait for the encoder command (default: 300 seconds)
   - **Regenerate Shellcode** — If the inner payload already has a Dolos wrapper, rebuild with a new UUID
4. **Step 3**: Select the inner payload to wrap
5. Click **Submit** to build

### Encoder Profiles

Encoder profiles are flat JSON files in `/Mythic/` inside the Dolos container. Each file starts with `00_` (the group number):

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
    "notes": "Windows-only encoder"
}
```

| Field | Description |
|-------|-------------|
| `label` | Display name in Mythic UI dropdown |
| `enabled` | Set `false` to hide from the dropdown |
| `command` | Remote command with `{workdir}`, `{input}`, `{output}` placeholders |
| `ssh_host` / `ssh_port` | Remote encoder server address |
| `ssh_username` | SSH login username |
| `ssh_password` | Password auth (empty string for key-only) |
| `ssh_key_enabled` | Set `true` to use SSH key from Mythic User Secrets |
| `ssh_key_secret` | Name of the Mythic User Secret containing the PEM private key |
| `timeout` | Seconds to wait for the encoder command |
| `success_string` | String in stdout confirming success |
| `fail_string` | String in stdout/stderr indicating failure |
| `install_tools` | Run install script before encoding |
| `bypass_refs` | Names of bypass profile files |

To add a second encoder, create `01_Encoder_OtherName.json` with group number `01`.

### SSH Authentication

| Method | Profile Config | Mythic UI |
|--------|---------------|-----------|
| **Password** | Set `ssh_password` in profile JSON | None needed |
| **SSH Key** | `ssh_key_enabled: true`, `ssh_password: ""` | Add key PEM as User Secret with name matching `ssh_key_secret` |

SSH keys are injected at build time via Mythic's secrets API — no key files stored on disk.

### Bypass Profiles

Bypass profiles are additional JSON files referenced by `bypass_refs` in the encoder profile. They let you define different encoding strategies (e.g., AMSI bypass, ETW patching) that appear as a dropdown in the Mythic UI.

### Tool Installation

If `install_tools: true`, Dolos will run the matching install script (`00_Tool_<encoder>_install.ps1` for Windows, `.sh` for Linux) on the remote server before encoding. This ensures the encoder executable is present. The install is idempotent — safe to run multiple times.

### Session Logging

Every build produces a `.session.json` artifact in Mythic. Download it from the build results — it contains a timestamped log of every SSH/SFTP operation, the encoder command, stdout/stderr, exit codes, and file magic detection.

### Paperclip UI (Live Config Editing)

All `00_*.json` files are visible and editable through the Mythic paperclip UI:

1. **Installed Services** → find Dolos → click the 📎 icon
2. Edit any profile file directly
3. Changes are detected on the next build (5-second poll cycle)

---

## Architecture

<details>
<summary>How Dolos works (click to expand)</summary>

```
  Mythic Server                    Dolos Container                Remote Server
  ┌─────────┐                     ┌─────────────┐               ┌─────────────┐
  │ Create   │ ──── payload ────▶ │ ① SSH auth  │               │             │
  │ Wrapper  │                     │ ② SFTP upload│ ── payload ──▶│ encoder.py  │
  │          │                     │ ③ Run install│ ── script ───▶│ C:\tools\   │
  │          │                     │ ④ SSH exec   │ ── command ──▶│ .exe → .bin │
  │          │                     │ ⑤ SFTP down  │ ◀─ result ────│ output.bin  │
  │          │ ◀── result + log ── │ ⑥ Cleanup   │               │             │
  └─────────┘                     └─────────────┘               └─────────────┘
```

</details>

---

## Installation

### Prerequisites

- Mythic 3.x (tested on 3.3+)
- A remote encoder server accessible over SSH
- Your encoder tooling installed (or use `install_tools: true`)

### Install

```bash
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

### Uninstall

```bash
sudo ./mythic-cli uninstall dolos
```

---

## Included Encoder

Dolos ships with **PyEncoder** — a Python-based encoder that uses the Windows C# compiler (`csc.exe`) to create a .NET cradle that loads and executes shellcode.

Files in `/Mythic/`:
- `00_Encoder_PyEncoder.json` — encoder profile (paperclip-editable)
- `00_Tool_pyencoder_encode.py` — encoder script (paperclip-editable)
- `00_Tool_pyencoder_install.ps1` — install script (paperclip-editable)

Deploy the encoder to your remote server:

```powershell
scp 00_Tool_pyencoder_encode.py operator@192.168.1.100:C:/tools/dolos/encoder.py
```

---

## Changelog

- **v2.1.0** — Clean public release. Removed dev docs, cleaned up gitignore, updated documentation for v2.
- **v2.0.0** — Flat-file configs at `/Mythic/` root. Mythic User Secrets for SSH keys. Paperclip-editable. Fixed sync spam bug.
- **v1.0.x** — Initial releases, MythicMeta compliance, Docker Hub publishing.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Authors

- [@3mrgnc3](https://github.com/3mrgnc3/Dolos)