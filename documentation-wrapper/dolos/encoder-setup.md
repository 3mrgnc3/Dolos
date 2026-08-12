+++
title = "Encoder Setup"
weight = 15
+++

## Encoder Setup

Dolos connects to a remote server over SSH/SFTP, runs your encoder command,
and returns the result. The encoder does all the work — Dolos just transfers
files and manages the session.

### Included Encoder

Dolos ships with a Python-based encoder (`00_Tool_pyencoder_encode.py`) that
uses the Windows C# compiler (`csc.exe`) to create a .NET cradle that loads
and executes shellcode. It's available via the paperclip UI in the Dolos container.

### Deploying the Encoder

```bash
scp 00_Tool_pyencoder_encode.py operator@192.168.1.100:C:/tools/dolos/encoder.py
```

If `install_tools: true` is set in the encoder profile, Dolos will automatically
run the install script on the remote server before encoding.

### Encoder Command Template

The `{workdir}`, `{input}`, and `{output}` placeholders are replaced at build time:

```
py.exe C:\tools\dolos\encoder.py {workdir}\{input} {workdir}\{output}
```

### SSH Authentication

**Password**: Set in the encoder profile JSON (`ssh_password`).

**SSH Key (recommended)**:
1. Add your private key PEM in Mythic UI → Settings → Secrets
2. Set `ssh_key_secret` to match the secret name (e.g., `DOLOS_00_ENCODER_SSH_KEY`)
3. Set `ssh_key_enabled: true` and `ssh_password: ""`

The key is injected at build time — no key files needed on disk.