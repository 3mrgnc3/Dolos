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

**Possible causes:**
1. **Browser notifications snoozed** - Check your browser's notification settings
2. **UI refresh delay** - Navigate away from the payload page and back to see updated step status

### SSH Connection Failed

**Symptom:** Build step shows ❌ for SSH connectivity.

**Possible causes:**
1. **Wrong credentials** - Check the `ssh_server` section in the encoder profile
2. **Wrong host/port** - Verify `ssh_server.host` and `ssh_server.port` match your server
3. **Key auth failure** - If `keys.enabled` is true, ensure `keys.path` points to a valid
   private key file (relative to the profile JSON). The key content is loaded at startup.
4. **Network unreachable** - From the container, can you reach the SSH server?
   ```
   docker exec dolos python3 -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('192.168.1.100', 22)); print('OK')"
   ```

**Fix:** Edit the encoder profile in `configs/encoders/` and reinstall the container.

### Container Logs

The Dolos container writes two types of logs:
1. **`docker logs dolos`** - Only CRITICAL severity (build start/end, hard errors). This is
   what mythic_container's root logger passes through.
2. **File logs at `/tmp/dolos/dolos.log`** - DEBUG and above. All SSH/SFTP events, encoder
   output, connection details. Rotating (50MB max, 3 backups).

To access file logs: `docker exec dolos cat /tmp/dolos/dolos.log`

To configure: set `DOLOS_LOG_DIR`, `DOLOS_LOG_MAX_MB`, `DOLOS_LOG_MAX_BACKUPS` in `.env`.

If file logs are not appearing, check that `/tmp/dolos/` is writable inside the container.

### Password Authentication Failed

**Symptom:** SSH connects but auth fails (❌ for password auth).

**Causes and fixes:**
1. **Wrong password** - Check `ssh_server.password` in the encoder profile
2. **Wrong username** - Check `ssh_server.username` in the encoder profile
3. **Password auth disabled on server** - Enable `PasswordAuthentication yes` in
   `sshd_config` and restart SSH, or use key auth instead

### SFTP Write Test Failed

**Symptom:** SSH connects and authenticates, but file upload fails.

**Causes and fixes:**
1. **Permission denied on remote directory** - The SSH user needs write access to
   the temp directory (`C:\Windows\Temp` on Windows, `/tmp` on Linux)
2. **Disk full** - Check available space on the remote server
3. **SFTP subsystem disabled** - Some servers disable SFTP. Check `sshd_config`:
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

**Fix:** Ensure the encoder binary/script exists at the path specified in the
profile's `command` field and is executable by the SSH user.

For the built-in C# cradle encoder:
- Verify `py.exe` (Python launcher) is in PATH: `py --version`
- Verify `csc.exe` exists: `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /?`
- Verify `C:\tools\encoder.py` exists on the remote server

### Encoder Returns Failure

**Symptom:** Build step shows `Fail String detected: ENCODING_FAILED` or non-zero exit code.

**Debug steps:**
1. Download the `.session.json` file from the build's Files tab - it contains the
   full timestamped log with every stdout/stderr line
2. Check the exact command that was run (look for `phase: "processing", level: "CMD"` events)
3. SSH to the remote server and run the encoder command manually
4. Verify the encoder prints `ENCODING_SUCCESS` on success
5. Check that file paths in the command are accessible

### No Encoder Profiles Configured

**Symptom:** Encoder dropdown shows "(no profiles configured)" and builds fail.

**Fix:** The `configs/encoders/` directory has no `encoder_profile.json` files.
Either:
1. Edit the auto-scaffolded sample profile at `configs/encoders/pyencoder/encoder_profile.json`
2. Create new profile directories under `configs/encoders/`

Then reinstall the container.

### Bypass Profile Dropdown Not Showing

**Symptom:** The Bypass Profile field is hidden even when it should appear.

**Fix:** This happens when the encoder profile doesn't have `bypass_profiles` set,
or the path doesn't point to an existing directory with `.json` files. Check:
1. The `bypass_profiles` field in the profile is set to a relative path (e.g., `"../bypass_profiles"`)
2. The directory exists relative to the profile JSON
3. The directory contains `.json` files (these become the dropdown options)

After editing profiles, reinstall the container for changes to take effect.

### No C2 Profile Section

**Symptom:** The Create Wrapper dialog doesn't show a C2 profile selection step.

**This is correct behavior.** Dolos is a wrapper payload type. The wrapped payload
already has its C2 profile embedded - Dolos just transforms the payload file.
No C2 selection is needed.

### Container Won't Start

**Symptom:** `docker logs dolos` shows connection errors or crashes.

**Debug steps:**
1. Check `docker logs dolos` for error messages
2. Verify the encoder profiles are valid JSON
3. Verify `HASURA_SECRET` and `HASURA_HOST` are set in `.env`
4. Try reinstalling: uninstall → full_uninstall → install

### .NET Framework Missing on Target

**Symptom:** Generated EXE fails to run on target with "requires .NET Framework" error.

**Fix:** The C# cradle encoder produces .NET Framework 4.x executables. Windows 10/11
includes this by default. On older Windows, install .NET Framework 4.8 from Microsoft.
For pure native payloads (no .NET dependency), use a different encoder
(e.g., ShellcodePack with native output, or MinGW-compiled C stub).

### How to Update Dolos

```bash
cd /home/mrgnc/MythicC2/Mythic

# 1. Uninstall current version
./mythic-cli uninstall dolos

# 2. Clean DB entries and stop container
bash /home/mrgnc/MythicC2/Dolos/dev_tools/remote/full_uninstall.sh

# 3. Install new version (fresh build, no cached layers)
./mythic-cli install folder ../Dolos
```

**Important:** Always do a full uninstall + reinstall. Do not just restart -
Docker image layer caching can cause stale code to persist.

### How to Update Encoder Profiles

1. Edit `configs/encoders/*/encoder_profile.json` files on the host
2. For Docker: the configs directory is bind-mounted, so changes take effect on
   container restart. For the encoder dropdown to update, you must restart the container:
   ```bash
   docker restart dolos
   ```
3. For local debug: restart the debug process

## Getting Help

- GitHub: https://github.com/3mrgnc3/Dolos
- Mythic Docs: https://docs.mythic-c2.net/