+++
title = "Troubleshooting"
weight = 50
+++

## Common Issues

### Zero-Byte Payload Files

**Symptom:** Build completes with "success" status but the downloaded file is 0 bytes.

**Cause:** The Mythic Python container framework's `BuildResponse` class stores the
downloadable file content in `self.payload` (lowercase). Setting `self.Payload` (uppercase)
creates a shadow attribute that `get_payload()` never reads.

**Fix:** This was fixed in v0.5.1. If you see zero-byte payloads, ensure you are
running v0.5.1 or later.

### Build Step Animations Not Visible

**Symptom:** Build completes but progress bubbles don't animate in the UI.

**Possible causes:
1. **Browser notifications snoozed** — Check your browser's notification settings
2. **UI refresh delay** — Navigate away from the payload page and back to see updated step status

### SSH Connection Failed

**Symptom:** Build step shows ❌ for SSH connectivity.

**Causes and fixes:**

1. **Wrong host/IP** — Check `DOLOS_SSH_HOST` in `.env`
2. **Wrong port** — Check `DOLOS_SSH_PORT` in `.env` (default: 22)
3. **Firewall blocking** — Ensure the external server allows SSH connections from Mythic's network
4. **Server not running** — Verify the external server is accessible: `ssh user@host`

**Fix:** Update `.env` and reinstall:
```bash
cd /path/to/Mythic
./mythic-cli uninstall dolos
bash /path/to/Dolos/dev_tools/full_uninstall.sh
./mythic-cli install folder ../Dolos
```

### Password Authentication Failed

**Symptom:** SSH connects but auth fails (❌ for password auth).

**Causes and fixes:**

1. **Wrong password** — Check `DOLOS_SSH_PASSWORD` in `.env`
2. **Wrong username** — Check `DOLOS_SSH_USERNAME` in `.env`
3. **Password auth disabled on server** — Enable `PasswordAuthentication yes` in
   `sshd_config` and restart SSH

### SFTP Write Test Failed

**Symptom:** SSH connects and authenticates, but file upload fails.

**Causes and fixes:**

1. **Permission denied on remote directory** — The SSH user needs write access to
   the temp directory (`C:\Windows\Temp` on Windows, `/tmp` on Linux)
2. **Disk full** — Check available space on the remote server
3. **SFTP subsystem disabled** — Some servers disable SFTP. Check `sshd_config`:
   ```
   Subsystem sftp /usr/lib/openssh/sftp-server
   ```

### Wrapped Payload Not in List

**Symptom:** The "Select a payload" dropdown in Create Wrapper doesn't show
the payload you just built.

**Causes and fixes:**

This happens when the payload type isn't in Dolos's `wrapped_payloads` list.
Dolos can only wrap payloads of types it explicitly supports. The current list is:
`apollo, merlin, athena, medusa, hannibal, freyja, poopsie, poseidon`.

To add a new agent type, edit `wrapped_payloads` in `builder.py` and reinstall Dolos.

### Encoder Command Not Found

**Symptom:** Build fails with exit code 127 or "command not found" in stderr.

**Fix:** Ensure the encoder binary/script exists at the path specified in your
`DOLOS_REMOTE_COMMAND` and is executable by the SSH user.

For the built-in C# cradle encoder:
- Verify `py.exe` (Python launcher) is in PATH: `py --version`
- Verify `csc.exe` exists: `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /?`
- Verify `C:\tools\encoder.py` exists on the remote server

### Encoder Returns Failure

**Symptom:** Build step shows `Fail String detected: ENCODING_FAILED` or non-zero exit code.

**Debug steps:**
1. Download the `.session.json` file from the build's Files tab — it contains the
   full timestamped log with every stdout/stderr line
2. Check the exact command that was run (look for `phase: "processing", level: "CMD"` events)
3. SSH to the remote server and run the encoder command manually
4. Verify the encoder prints `ENCODING_SUCCESS` on success
5. Check that file paths in the command are accessible

### csc.exe Errors (Large Payloads)

**Symptom:** Encoder fails with CS0013 or CS1647 on large shellcode (>1MB).

**This should not happen with encoder v2.2+** — it uses `.resources` embedding
instead of base64 string literals. If you see these errors, ensure you're running
`dev_tools/encoder/encoder.py` (deployed as `C:\tools\encoder.py`), not an older version.

### No C2 Profile Section

**Symptom:** The Create Wrapper dialog doesn't show a C2 profile selection step.

**This is correct behavior.** Dolos is a wrapper payload type. The wrapped payload
already has its C2 profile embedded — Dolos just transforms the payload file.
No C2 selection is needed.

### Container Won't Start

**Symptom:** `docker logs dolos` shows connection errors or crashes.

**Debug steps:**
1. Check `docker logs dolos` for error messages
2. Verify `.env` has all `DOLOS_*` variables
3. Verify `HASURA_SECRET` and `HASURA_HOST` are set
4. Try reinstalling: uninstall → full_uninstall → install

### .NET Framework Missing on Target

**Symptom:** Generated EXE fails to run on target with "requires .NET Framework" error.

**Fix:** The C# cradle encoder produces .NET Framework 4.x executables. Windows 10/11
includes this by default. On older Windows, install .NET Framework 4.8 from Microsoft.
For pure native payloads (no .NET dependency), use a different encoder
(e.g., ShellcodePack with native output, or MinGW-compiled C stub).

### How to Update Dolos

```bash
cd /path/to/Mythic

# 1. Uninstall current version
./mythic-cli uninstall dolos

# 2. Clean DB entries
bash /path/to/Dolos/dev_tools/full_uninstall.sh

# 3. Install new version
./mythic-cli install folder ../Dolos

# 4. Verify
docker logs dolos
```

### How to Update Encoder Commands

1. Edit `DOLOS_REMOTE_COMMAND` in `/path/to/Mythic/.env`
2. Reinstall the container (see above)

## Getting Help

- GitHub: https://github.com/3mrgnc3/Dolos
- Mythic Docs: https://docs.mythic-c2.net/