# Dolos v2 — Flat File Naming Convention

## Core Principle

The filename encodes everything you need to know for display, ordering, and grouping. You never need to open a file to list encoders, show them in a UI, or know what type something is. Only when building a payload do you read the contents.

## Naming Convention

```
{NN}_{Type}_{Detail}.{ext}
```

- **NN** — Two-digit sort order (00-99). All files with the same number belong to the same encoder group.
- **Type** — One of: `Encoder`, `Bypass`, `Tool`, `SSHKey`
- **Detail** — Human-readable label, underscores for spaces
- **ext** — `.json` for configs, no extension for keys, `.sh`/`.ps1` for scripts

## Examples

```
/Mythic/configs/
├── 00_Encoder_PyEncoder.json          ← Encoder profile, group 00
├── 00_Bypass_AMSI.json               ← Bypass profile for encoder 00
├── 00_Tool_pyencoder_linux.sh        ← Tool installer for encoder 00 (Linux)
├── 00_Tool_pyencoder_windows.ps1     ← Tool installer for encoder 00 (Windows)
├── 00_SSHKey_operator_id_rsa          ← SSH key for encoder 00
├── 01_Encoder_Donut.json             ← Second encoder, group 01
├── 01_Tool_donut_linux.sh            ← Tool for encoder 01
└── 01_SSHKey_jumpserver_id_rsa       ← SSH key for encoder 01
```

## What the filename tells you (no file open needed)

| Filename | Group | Type | Label | Sort |
|----------|-------|------|-------|------|
| `00_Encoder_PyEncoder.json` | 00 | Encoder | PyEncoder | 0 |
| `00_Bypass_AMSI.json` | 00 | Bypass | AMSI | 0 |
| `00_Tool_pyencoder_linux.sh` | 00 | Tool | pyencoder (Linux) | 0 |
| `01_Encoder_Donut.json` | 01 | Encoder | Donut | 1 |

Enumerating configs = `os.listdir('/Mythic/configs/')` + parse filenames. Done.

## What's inside each file type

### `NN_Encoder_{Label}.json`
```json
{
    "version": 2,
    "label": "PyEncoder",
    "enabled": true,
    "command": "python3 /tools/encoder.py {workdir}/{input} {workdir}/{output}",
    "ssh_host": "192.168.1.100",
    "ssh_port": 22,
    "ssh_username": "operator",
    "ssh_password": "",
    "ssh_key_ref": "${00_SSHKey_operator_id_rsa}",
    "ssh_key_enabled": true,
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "bypass_refs": ["00_Bypass_AMSI.json"],
    "notes": "Default encoder"
}
```

Key differences from v1:
- **Flat** — `ssh_host` not nested under `ssh_server`
- **`ssh_key_ref`** — Uses `${VAR}` syntax referencing the SSH key filename with `SSHKey_` prefix. Resolved at build time from Mythic user secrets OR from the key file in configs/.
- **`bypass_refs`** — References bypass profiles by **filename**, not directory path
- **`install_tools`** — Still boolean, but tool scripts are found by matching `NN_Tool_*` files to the encoder's group number

### `NN_Bypass_{Label}.json`
```json
{
    "version": 2,
    "label": "AMSI Bypass",
    "enabled": true,
    "config": {
        "technique": "amsi_init_failed",
        "target_os": "windows"
    }
}
```

Just a labeled JSON blob. The encoder references it by filename. The builder uploads the contents to the SSH workdir.

### `NN_SSHKey_{Label}` (no extension)
Raw PEM private key. Read at build time. Also available as a Mythic user secret reference point.

### `NN_Tool_{Label}_{os}.{sh|ps1}`
Executable script. SFTP'd to the remote server before encoding if `install_tools: true`.

## Resolution at Build Time

When building a payload:
1. Parse filename → know type, group, label, sort order
2. Read encoder JSON → get command, SSH details, bypass refs
3. Resolve `${NN_SSHKey_*}` references → look up in Mythic user secrets first, fall back to file content in configs/
4. Read bypass JSON files referenced by filename
5. Upload tool scripts for the matching group number
6. Execute

## What Gets Removed

- ❌ Directory structure (encoders/, ssh_keys/, tools/, bypass_profiles/)
- ❌ Relative path resolution (../../ssh_keys/test_key)
- ❌ Directory traversal in config_loader.py
- ❌ The `dolos_profiles` bind mount volume
- ❌ Scaffolding system (no more empty volumes to populate)
- ❌ `.gitkeep` files
- ❌ `SETUP.md` files in tool directories

## What Gets Added

- ✅ Flat file naming with `NN_Type_Detail.ext` convention
- ✅ `${VAR}` secret resolution via Hasura
- ✅ Filenames as metadata — enumerate without reading
- ✅ Clear error messages in build output
- ✅ Paperclip-friendly — all files under `/Mythic/configs/`, editable via Mythic UI