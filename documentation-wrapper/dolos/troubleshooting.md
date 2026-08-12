+++
title = "Troubleshooting"
weight = 30
+++

## Troubleshooting

### Container doesn't start / not in installed services

1. Check container logs: `sudo docker logs dolos`
2. Common causes:
   - Missing encoder profile — Dolos needs at least one `00_*.json` file in `/Mythic/`
   - Syntax error in profile JSON — validate with `python3 -m json.tool`

### "No encoder profiles configured"

The `00_*.json` files must be in `/Mythic/` inside the container. If using a
bind mount (`use_volume: true`), make sure the mount directory contains the config
files. If using the pre-built image, configs are baked into `/Mythic/` and are
editable via the paperclip UI.

### SSH connection failed

- Verify `ssh_host` and `ssh_port` in the encoder profile
- For password auth: set `ssh_password`
- For key auth: add the private key PEM as a User Secret in Mythic UI and set
  `ssh_key_secret` to the secret name
- Set `ssh_key_enabled: true` when using key auth

### Session log

Every build produces a `.session.json` artifact in Mythic. Download it from the
build results — it contains a timestamped log of every SSH/SFTP operation,
the encoder command, stdout/stderr, exit codes, and file magic detection.

### Reinstalling

```bash
sudo ./mythic-cli uninstall dolos
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```