+++
title = "Troubleshooting"
weight = 30
+++

## Troubleshooting

### Container doesn't start / not in installed services

1. Check container logs: `sudo docker logs dolos`
2. Common causes:
   - Missing encoder profile — Dolos needs at least one `NN_*.json` file in `/Mythic/`
   - Syntax error in profile JSON — validate with `python3 -m json.tool` inside the container
   - RabbitMQ not connected — ensure Mythic's RabbitMQ container is running: `sudo docker ps | grep rabbitmq`

### "No encoder profiles configured"

The `NN_*.json` files must be in `/Mythic/` inside the container. If using the paperclip UI,
they're editable directly. If files are missing:

1. Go to **Installed Services** → Dolos → 📎 (paperclip icon)
2. Check that at least one `00_*.json` encoder profile exists
3. Verify `enabled: true` in the profile
4. Verify valid JSON syntax

### SSH connection failed

When you create a wrapper build, Dolos automatically tests the SSH connection and reports:

- ✅ **SSH connectivity** — Can reach the server
- ✅ **Key/password authentication** — Credentials accepted
- ✅ **SFTP write test** — Can upload and delete a test file

If authentication fails:

**For password auth**: Set `ssh_password` in the encoder profile JSON.

**For SSH key auth (recommended)**:
1. Add your private key PEM in Mythic UI → Settings → Secrets
2. Set `ssh_key_secret` to the secret name (e.g., `DOLOS_00_ENCODER_SSH_KEY`)
3. Set `ssh_key_enabled: true` and `ssh_password: ""`

Common SSH key issues:
- **Key format**: Must be PEM format (starts with `-----BEGIN OPENSSH PRIVATE KEY-----` or `-----BEGIN RSA PRIVATE KEY-----`)
- **Secret name**: Must match exactly between `ssh_key_secret` in the profile and the User Secret name
- **Key permissions**: Ensure the key isn't password-protected (Dolos can't enter a passphrase)

### Encoder command failed

Check the **session log** artifact (`.session.json`) in the build results. It contains:

- The exact SSH command executed
- Line-by-line stdout and stderr from the encoder
- The exit code
- File magic detection of the output
- Timestamps for every SSH/SFTP operation

Common issues:
- **Encoder not found on remote server**: Ensure tools are installed at the path in `command`
- **Timeout too low**: Increase `timeout` in the profile or use the Timeout build parameter
- **Missing `success_string`/`fail_string`**: Your encoder must print one of these to stdout

### Excessive sync event messages in event feed

This was a known bug in v1.x. The `_profile_mtimes` dictionary wasn't tracking all config files,
causing a resync on every 5-second poll cycle. This is fixed in v2.0+. If you see excessive
"synced dolos" messages, ensure you're running v2.0.0 or later.

### Paperclip UI can't see config files

Config files must be at `/Mythic/` root (not in subdirectories). In v2, configs are flat
JSON files named `NN_Label.json`. Paperclip can only navigate the root directory.

If configs were in `/Mythic/configs/` (v1 layout), they need to be moved to `/Mythic/`.

### Regenerate Shellcode checkbox

If you see "This payload already has a Dolos wrapper" error, check the
**Regenerate Shellcode** checkbox in the build dialog. This tells Dolos to re-wrap the
payload with a fresh UUID instead of failing on a duplicate.

### Reinstalling Dolos

```bash
sudo ./mythic-cli uninstall dolos
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

Config files in `/Mythic/` are preserved in the Docker volume across reinstalls.
Encoder profiles edited via paperclip will persist.

### Session Log Format

Every build produces a `.session.json` artifact with full forensic detail:

```json
{
  "payload_name": "apollo_20260812_145623",
  "encoder": "ShellcodePack",
  "events": [
    {"ts": "2026-08-12T14:56:23Z", "op": "ssh_connect", "host": "192.168.1.100", "status": "ok"},
    {"ts": "2026-08-12T14:56:23Z", "op": "ssh_auth", "method": "key", "status": "ok"},
    {"ts": "2026-08-12T14:56:24Z", "op": "sftp_upload", "file": "payload.bin", "bytes": 28672, "status": "ok"},
    {"ts": "2026-08-12T14:56:24Z", "op": "ssh_exec", "cmd": "shellcodepack.exe -i ...", "status": "running"},
    {"ts": "2026-08-12T14:56:28Z", "op": "ssh_exec_result", "exit_code": 0, "stdout": "ENCODING_SUCCESS", "status": "ok"},
    {"ts": "2026-08-12T14:56:28Z", "op": "sftp_download", "file": "payload.exe", "bytes": 45056, "status": "ok"},
    {"ts": "2026-08-12T14:56:28Z", "op": "sftp_cleanup", "status": "ok"}
  ]
}
```