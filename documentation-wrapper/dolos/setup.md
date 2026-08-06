+++
title = "Setup"
weight = 10
+++

## How Configuration Works

Dolos uses **file-based configuration** instead of environment variables. All SSH credentials,
encoder commands, and bypass profiles are stored in the `configs/` directory, which is
bind-mounted into the Dolos container at `/Mythic/configs/`.

### Directory Structure

```
configs/
├── encoders/
│   ├── pyencoder/
│   │   └── encoder_profile.json     ← basic encoder, auto-scaffolded on first run
│   ├── balliskit/
│   │   ├── macropack/
│   │   │   └── encoder_profile.json  ← MacroPack encoder profile
│   │   ├── shellcodepack/
│   │   │   └── encoder_profile.json ← ShellcodePack encoder profile
│   │   ├── bypass_profiles/
│   │   │   ├── cortex_bypass_profile.json
│   │   │   └── s1_bypass_profile.json
│   │   └── id_ed25519              ← SSH key for this server
│   └── donut_x64/
│       └── encoder_profile.json     ← Donut encoder profile
└── ssh_keys/
    ├── tiny11/
    │   ├── id_ed25519              ← SSH private key
    │   └── id_ed25519.pub          ← SSH public key (not used for auth)
    └── ubuntuSVR01/
        ├── ssh_key                 ← SSH private key
        └── ssh_key.pub             ← SSH public key
```

Inside Docker: `/Mythic/configs/` (via the existing bind mount).
Local debug: `DOLOS_CONFIG` points to the repo's `Payload_Type/dolos/configs/`.

### encoder_profile.json Schema

Each encoder has its own directory under `configs/encoders/` containing an
`encoder_profile.json` file. This defines the SSH connection, command template,
and optional bypass profiles.

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
        "keys": {
            "enabled": true,
            "path": "../../ssh_keys/tiny11/id_ed25519"
        }
    },
    "timeout": 300,
    "bypass_profiles": ""
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `index` | int | No | Display order (lower = first). Default 0. |
| `label` | string | Yes | Name shown in the Mythic Encoder dropdown. |
| `command` | string | Yes | Command template with placeholders. Must contain `{input}` and `{output}`. |
| `ssh_server.host` | string | Yes | Hostname or IP of the remote SSH server. |
| `ssh_server.port` | int | No | SSH port. Default 22. |
| `ssh_server.username` | string | Yes | SSH username. |
| `ssh_server.password` | string | No | SSH password. Can be empty if using key auth. |
| `ssh_server.keys.enabled` | bool | No | Whether to use SSH key auth. Default false. |
| `ssh_server.keys.path` | string | No | Relative path from the profile JSON to the private key file. |
| `timeout` | int | No | Command timeout in seconds. Default 300. |
| `bypass_profiles` | string | No | Relative path from the profile JSON to a directory of bypass profile JSON files. |

**Note:** The field name `"lable"` (a common typo) is also accepted and normalized to `label`.

### Key Authentication

SSH key files are stored in `configs/ssh_keys/` (or alongside the encoder profile).
The `keys.path` field is resolved **relative to the encoder_profile.json file**.

Examples:
- `"path": "../../ssh_keys/tiny11/id_ed25519"` — two directories up, into shared SSH keys
- `"path": "../id_ed25519"` — key file in the same parent directory as the encoder profile
- `"path": ""` — no key file (use password auth only)

At least one auth method must be configured: password, key, or both.

### Bypass Profiles

Some encoders (like ShellcodePack) support bypass profiles for EDR evasion. These are
JSON files stored in a `bypass_profiles/` directory. When an encoder has bypass profiles,
the **Bypass Profile** dropdown appears in the build dialog.

The `bypass_profiles` field in the profile JSON points to the directory containing
profile files. The `{bypass_profile}` placeholder in the command template resolves to
the selected profile's stem name (filename without `.json`).

Example encoder with bypass profiles:
```json
{
    "index": 3,
    "label": "ShellcodePack_v2.6",
    "command": "C:\\tools\\shellcodepack.exe -i {workdir}\\{input} -o {workdir}\\{output} --profile C:\\tools\\profiles\\{bypass_profile}.json",
    "ssh_server": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "operator",
        "password": "",
        "keys": {"enabled": true, "path": "../id_ed25519"}
    },
    "timeout": 600,
    "bypass_profiles": "../bypass_profiles"
}
```

The bypass profiles dropdown shows entries like **"ProjectName / ProfileName Bypass"**.

### Auto-Scaffolding

If the `configs/` directory is missing or contains no encoder profiles, Dolos
auto-creates a sample `PyEncoder_v1` profile with placeholder SSH credentials.
This gives operators a starting template to customize immediately after install.

## Setting Up Password Authentication

1. Edit the encoder profile's `ssh_server` section:
   ```json
   {
       "ssh_server": {
           "host": "192.168.1.100",
           "port": 22,
           "username": "operator",
           "password": "your_password_here",
           "keys": {"enabled": false, "path": ""}
       }
   }
   ```
2. Reinstall: `mythic-cli uninstall dolos && mythic-cli install folder ../Dolos`

## Setting Up Key Authentication

1. Generate or copy an SSH key pair into `configs/ssh_keys/`:
   ```
   configs/ssh_keys/tiny11/id_ed25519       ← private key
   configs/ssh_keys/tiny11/id_ed25519.pub   ← public key (reference only)
   ```
2. Reference the key from the encoder profile using a relative path:
   ```json
   {
       "ssh_server": {
           "keys": {"enabled": true, "path": "../../ssh_keys/tiny11/id_ed25519"}
       }
   }
   ```
3. Reinstall the container.

## Verifying Connectivity

When you create a wrapper, Dolos automatically tests the SSH connection.
The build progress shows:
- ✅ SSH connectivity
- ✅ Key/password authentication
- ✅ SFTP write test (upload + delete a small test file)

If any step fails, you'll see ❌ with an error message and instructions.

## Adding a New Encoder Profile

1. Create a new directory under `configs/encoders/`:
   ```
   configs/encoders/my_encoder/encoder_profile.json
   ```
2. Fill in the profile JSON with your SSH server and command template
3. Reinstall the container: `mythic-cli uninstall dolos && mythic-cli install folder ../Dolos`
4. The new encoder appears in the **Encoder** dropdown

## Environment Variables

Only infrastructure-level env vars remain (all SSH and encoder config is in files):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DOLOS_CONFIG` | No | `/Mythic/configs` | Path to configs directory |
| `DOLOS_LOG_DIR` | No | `/tmp/dolos` | Log file directory |
| `DOLOS_LOG_MAX_MB` | No | `50` | Max log file size in MB |
| `DOLOS_LOG_MAX_BACKUPS` | No | `3` | Number of rotated log files |
| `HASURA_SECRET` | Yes | — | Hasura admin secret |
| `HASURA_HOST` | No | `mythic_graphql` | Hasura hostname |
| `HASURA_PORT` | No | `8080` | Hasura port |