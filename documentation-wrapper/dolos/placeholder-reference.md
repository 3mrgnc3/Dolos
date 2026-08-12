+++
title = "Reference"
weight = 40
+++

## Encoder Profile Schema (v2)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | int | yes | Must be `2` |
| `label` | string | yes | Display name in Mythic UI |
| `enabled` | bool | yes | `false` hides from dropdown |
| `command` | string | yes | Encoder command with `{workdir}`, `{input}`, `{output}` placeholders |
| `ssh_host` | string | yes | Remote server hostname/IP |
| `ssh_port` | int | yes | SSH port (default: 22) |
| `ssh_username` | string | yes | SSH username |
| `ssh_password` | string | no | Password auth (empty string for key-only) |
| `ssh_key_enabled` | bool | no | Set `true` to use SSH key auth |
| `ssh_key_secret` | string | no | Mythic User Secret name containing the PEM private key |
| `timeout` | int | yes | Command timeout in seconds |
| `success_string` | string | yes | String in stdout confirming success |
| `fail_string` | string | yes | String in stdout/stderr indicating failure |
| `install_tools` | bool | no | Run install script before encoding |
| `bypass_refs` | array | no | Names of bypass profile files to include |
| `notes` | string | no | Operator notes (not used by Dolos) |