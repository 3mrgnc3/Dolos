+++
title = "Reference"
weight = 40
+++

## Encoder Profile Schema (v2)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | int | yes | — | Must be `2`. Identifies the config schema version. |
| `label` | string | yes | — | Display name in Mythic UI dropdown. |
| `enabled` | bool | yes | — | Set `false` to hide from the dropdown without deleting the profile. |
| `command` | string | yes | — | Remote command template with `{workdir}`, `{input}`, `{output}`, and optionally `{bypass_profile}` placeholders. |
| `ssh_host` | string | yes | — | Hostname or IP of the remote SSH server. |
| `ssh_port` | int | no | `22` | SSH port. |
| `ssh_username` | string | yes | — | SSH username. |
| `ssh_password` | string | no | `""` | Password for SSH auth. Empty when using key auth. |
| `ssh_key_enabled` | bool | no | `false` | Set `true` to authenticate with an SSH key from Mythic User Secrets. |
| `ssh_key_secret` | string | no | — | Name of the Mythic User Secret containing the PEM private key. Convention: `DOLOS_<NN>_ENCODER_SSH_KEY`. |
| `timeout` | int | no | `300` | Command timeout in seconds. Overridden by the Timeout build parameter when set > 0. |
| `success_string` | string | no | `"ENCODING_SUCCESS"` | String in stdout confirming successful encoding. |
| `fail_string` | string | no | `"ENCODING_FAILED"` | String in stdout/stderr indicating failure. |
| `install_tools` | bool | no | `false` | Whether to upload and run `NN_Tool_*` install scripts before encoding. |
| `bypass_refs` | array | no | `[]` | Names of bypass profile files (without `.json` extension). Presenting `["01_Bypass_AMSI"]` adds a Bypass Profile dropdown. |
| `notes` | string | no | — | Operator notes visible in paperclip UI. Not used by Dolos. |

## File Naming Convention

Files in `/Mythic/` follow the `NN_Type_Name.ext` pattern:

| Pattern | Example | Purpose |
|---------|---------|---------|
| `NN_Label.json` | `01_ShellcodePack.json` | Encoder profile |
| `NN_Tool_Name_install.ps1` | `01_Tool_shellcodepack_install.ps1` | Windows install script (uploaded when `install_tools: true`) |
| `NN_Tool_Name_install.sh` | `01_Tool_shellcodepack_install.sh` | Linux install script |
| `NN_Tool_Name.py` | `00_Tool_pyencoder_encode.py` | Encoder script (uploaded when matching group) |
| `NN_Bypass_Name.json` | `01_Bypass_AMSI.json` | Bypass profile (referenced by `bypass_refs`) |

The `NN` group number links files together. When encoder `01_ShellcodePack.json` has
`install_tools: true`, all files matching `01_Tool_*` are uploaded before encoding.

## Build Pipeline Steps

Dolos reports 9 build steps in the Mythic UI:

| Step | Name | Description |
|------|------|-------------|
| 1 | Connecting | SSH connect to remote server |
| 2 | Authenticating | SSH key/password authentication |
| 3 | SFTP write test | Upload + delete a test file |
| 4 | Checking payload | Validate the wrapped payload |
| 5 | Rebuilding | Regenerate shellcode if already wrapped |
| 6 | Uploading | SFTP upload the payload to remote workdir |
| 7 | Installing | Run install script if `install_tools: true` |
| 8 | Encoding | Execute the encoder command via SSH |
| 9 | Fetching | SFTP download the encoded result |

## Supported Output Formats

Dolos is **encoder-agnostic** — the output format depends entirely on your remote encoder:

| Encoder | Input | Output |
|---------|-------|--------|
| PyEncoder (included) | shellcode bin | EXE (C# cradle via csc.exe) |
| [ShellcodePack](https://balliskit.com/) | shellcode bin | EXE (with bypass profiles) |
| [MacroPack](https://balliskit.com/) | shellcode bin | Office macro document |
| donut | shellcode bin | EXE (shellcode runner) |
| Custom | any | any |

## Command Template Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{workdir}` | Temporary directory on the remote server | `C:\Windows\Temp\wd_a3f2\` |
| `{input}` | Filename of the uploaded payload in workdir | `payload.bin` |
| `{output}` | Desired output filename in workdir | `encoded.exe` |
| `{bypass_profile}` | Stem name of selected bypass profile (no extension) | `AMSI_bypass` |

Full command example:
```
C:\tools\shellcodepack.exe -i {workdir}\{input} -o {workdir}\{output} --profile C:\tools\profiles\{bypass_profile}.json
```

After substitution:
```
C:\tools\shellcodepack.exe -i C:\Windows\Temp\wd_a3f2\payload.bin -o C:\Windows\Temp\wd_a3f2\encoded.exe --profile C:\tools\profiles\AMSI_bypass.json
```