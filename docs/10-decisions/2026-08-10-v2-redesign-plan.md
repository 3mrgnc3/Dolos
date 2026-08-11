# Dolos v2 — Full Redesign Plan (Updated)

**Status**: In progress — v2.0.0 running, configs at /Mythic/ root  
**Branch**: `feature/ui-managed-configs`  
**Version**: v2.0.0 (breaking change)

---

## 1. Problem Statement

Dolos v1.x uses a **mounted volume + directory tree** pattern for configuration that has critical usability problems:

1. **Not editable via the Mythic UI** — Configs in a separate bind mount (`dolos_profiles/`) are invisible to the paperclip file browser. Operators must SSH into the Mythic host.
2. **Empty on first install** — Operators see "No valid encoder profiles found" until they manually create JSON files.
3. **Disabled samples with fake IPs** — `SAMPLE_PyEncoder` has `enabled: false` and `host: 192.168.1.100`. Operators don't know what to change.
4. **Directory management complexity** — Bypass profiles, SSH keys, and tools in nested subdirectories.
5. **SSH keys in plaintext files** — Private keys on the Mythic host filesystem, accessible to anyone with host access. No per-operator privacy.
6. **No UI feedback on config errors** — Errors buried in container logs. Operators see "(no profiles configured)".
7. **Dev environment ≠ production** — Local dev had files/structures that don't exist in a clean Docker install.

---

## 2. Architecture: Flat File Naming Convention

**Core principle**: The filename IS the metadata. No parsing needed until build time.

### Naming Format

```
{NN}_{Type}_{Detail}.{ext}
```

| Component | Description |
|-----------|-------------|
| **NN** | Two-digit sort order (00-99). Same number = same encoder group. |
| **Type** | `Encoder`, `Bypass`, `Tool`, `SSHKey` |
| **Detail** | Human-readable label, underscores for spaces |
| **ext** | `.json` for configs, no extension for keys, `.ps1`/`.sh` for scripts |

### Example

```
/Mythic/configs/
├── 00_Encoder_PyEncoder.json              
├── 00_Bypass_AMSI.json                   
├── 00_Tool_pyencoder_install.ps1         
├── 00_Tool_pyencoder_encode.py           
├── 01_Encoder_Donut.json                 
├── 01_Tool_donut_install.ps1             
└── 01_Tool_donut_encode.ps1             
```

**No SSH key files here.** SSH keys belong in Mythic's User Settings → Secrets, not in flat files.

---

## 3. SSH Key Management via Mythic User Secrets

**This is the critical design change.** Mythic has a built-in per-operator secret store:

- Operators add secrets in **Mythic UI → User Settings → Secrets**  
- Each secret has a name (e.g. `00_SSHKey_operator_id_rsa`) and a value (the private key PEM)
- Secrets are **per-user, private** — Operator A cannot see Operator B's secrets
- Mythic passes secrets to payload builds via `PayloadType.secrets` dict
- At build time, `self.secrets` contains the requesting operator's secrets

### How Dolos Uses Secrets

In the encoder profile JSON:
```json
{
    "version": 2,
    "label": "PyEncoder",
    "enabled": true,
    "command": "py.exe C:\\tools\\dolos\\encoder.py {workdir}\\{input} {workdir}\\{output}",
    "ssh_host": "192.168.1.50",
    "ssh_port": 22,
    "ssh_username": "operator",
    "ssh_password": "",
    "ssh_key_secret": "00_SSHKey_operator_id_rsa",
    "ssh_key_enabled": true,
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "bypass_refs": ["00_Bypass_AMSI.json"],
    "notes": "Windows-only encoder using py.exe. Add your SSH key in User Settings → Secrets."
}
```

The `ssh_key_secret` field references a **Mythic secret name**, not a file path. At build time, Dolos resolves it:

```python
# In builder.py build():
ssh_key_content = ""
if profile.ssh_key_secret:
    ssh_key_content = self.secrets.get(profile.ssh_key_secret, "")
    if not ssh_key_content:
        # Fall back: check if there's a file in /Mythic/configs/ with that name
        key_path = f"/Mythic/configs/{profile.ssh_key_secret}"
        if os.path.isfile(key_path):
            with open(key_path) as f:
                ssh_key_content = f.read()
```

**Resolution order:**
1. **Mythic User Secrets** (primary) — per-operator, private, managed via UI
2. **Flat file fallback** — for operators who prefer file-based config (still paperclip-editable)

**Documentation will recommend** using User Secrets as the primary method, with clear instructions:
1. Go to **Mythic UI → User Settings → Secrets**
2. Click **Add Secret**
3. Name: `00_SSHKey_operator_id_rsa`, Value: *(paste private key PEM)*
4. Add the corresponding public key to your SSH server's `authorized_keys`
5. In your encoder profile, set `ssh_key_secret` to `00_SSHKey_operator_id_rsa`

This eliminates the `ssh_keys/` directory entirely for most users.

---

## 4. Default Encoder: PyEncoder for Windows

### Shipped Default

`00_Encoder_PyEncoder.json` — **enabled by default**, nearly complete. Operator only needs to:
1. Add SSH credentials (host, username, and key in User Secrets)
2. Run the install script on their target Windows machine

The encoder uses `py.exe` (Windows Python launcher) and built-in Windows tools. **Windows-only — not portable to Linux.**

### Install Script: `00_Tool_pyencoder_install.ps1`

Legitimate tool setup for the target Windows machine:
1. Update winget: `winget source update`
2. Install Python 3: `winget install Python.Python.3.12`
3. Create `C:\tools\dolos\` directory
4. Copy the encoder script from the SFTP workdir to `C:\tools\dolos\encoder.py`

The install script is **not evasion** — it's standard Windows administration. The user enables PowerShell script execution (`Set-ExecutionPolicy RemoteSigned`) and runs it once on the target. The encoder script itself is a simple Python passthrough that reads input, optionally transforms, and writes output with the `ENCODING_SUCCESS` marker.

### Other Encoders: Documented, Not Shipped

- **Shellcode Ack (Liskit)** — Commercial product. Documentation includes a link to liskit.com and an example encoder profile JSON. Users create `02_Encoder_ShellcodeAck.json` themselves.
- **Donut** — Open source shellcode converter. Same pattern — documented with example profile, not shipped.

---

## 5. File Schemas

### `NN_Encoder_{Label}.json`

```json
{
    "version": 2,
    "label": "PyEncoder",
    "enabled": true,
    "command": "py.exe C:\\tools\\dolos\\encoder.py {workdir}\\{input} {workdir}\\{output}",
    "ssh_host": "",
    "ssh_port": 22,
    "ssh_username": "",
    "ssh_password": "",
    "ssh_key_secret": "00_SSHKey_operator_id_rsa",
    "ssh_key_enabled": true,
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "bypass_refs": ["00_Bypass_AMSI.json"],
    "notes": "Windows-only. Uses py.exe launcher. Add SSH key in User Settings → Secrets."
}
```

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

### `NN_Tool_{Label}.{ps1|sh|py}`

Executable scripts SFTP'd to remote host before encoding. Found by matching group number.

---

## 6. What Gets Removed

- ❌ Directory structure (`encoders/`, `ssh_keys/`, `tools/`, `bypass_profiles/`)
- ❌ Relative path resolution (`../../ssh_keys/test_key`)
- ❌ Directory traversal in `config_loader.py`
- ❌ `dolos_profiles` bind mount volume
- ❌ Scaffolding system (`_scaffold_sample_config()`, `_copy_defaults_into_config()`)
- ❌ `.gitkeep` and `SETUP.md` placeholder files
- ❌ Disabled sample profiles with fake IPs
- ❌ `_profile_mtimes` resync bug (entire approach simplified)
- ❌ SSH key files in configs directory (replaced by User Secrets)

---

## 7. What Gets Added

- ✅ **Flat file naming** with `NN_Type_Detail.ext` convention
- ✅ **SSH keys via Mythic User Secrets** — `ssh_key_secret` field references secret name, resolved via `self.secrets` at build time with flat file fallback
- ✅ **Filenames as metadata** — enumerate without reading file contents
- ✅ **Paperclip-friendly** — all files under `/Mythic/configs/`, editable via Mythic UI
- ✅ **Clear error messages** in build output (no more buried container logs)
- ✅ **Enabled-by-default PyEncoder** — only needs SSH credentials
- ✅ **PowerShell install script** for target Windows machines
- ✅ **Documentation for commercial tools** (Shellcode Ack, Donut) with links and example profiles

---

## 8. Persistent Config Across Reinstalls

`mythic-cli install github` overwrites `InstalledServices/`. Solution:

Dolos syncs config state to Mythic's `operationagentstorage` (key-value store via `SendMythicRPCAgentStorageCreate`/`Search`). On startup:
1. Load files from `/Mythic/configs/` (defaults baked into image)
2. Check agent_storage for overrides → merge
3. On config change (mtime trigger) → sync back to agent_storage
4. On reinstall → files overwritten but agent_storage persists → operator edits restored

---

## 9. Implementation Steps (After Approval)

### Phase 1: Clean Slate
1. `mythic-cli uninstall dolos` → `docker rm dolos && docker rmi <images>` → verify clean
2. Create branch `feature/ui-managed-configs` from `master`
3. Clone and sync to branch

### Phase 2: Structural Redesign
4. Redesign `config_loader.py` for flat file naming — parse filenames for type/group/label
5. Create v2 encoder profile schema (flat, `ssh_key_secret`, `bypass_refs` as filenames)
6. Create `00_Encoder_PyEncoder.json` (enabled, Windows-only, needs SSH creds)
7. Create `00_Tool_pyencoder_install.ps1` (winget-based Python install)
8. Create `00_Tool_pyencoder_encode.py` (the passthrough encoder script)
9. Remove `dolos_profiles` bind mount, directory traversal, scaffolding
10. Simplify mtime watcher for single flat directory
11. Add `self.secrets` resolution for SSH key in `builder.py`
12. Add clear error messages for missing secrets, invalid configs

### Phase 3: Agent Storage Sync
13. On startup: load files → check agent_storage for overrides → merge
14. On config change: sync to agent_storage
15. On reinstall: restore from agent_storage

### Phase 4: Documentation Overhaul
16. Remove all v1 directory structure docs
17. Write new setup guide: install → edit config via paperclip → add SSH secret → build
18. Write encoder creation guide
19. Document Shellcode Ack and Donut with example profiles
20. Document SSH key setup: User Settings → Secrets (primary) + paperclip fallback
21. Document Windows-only PyEncoder with install walkthrough

### Phase 5: Testing & Release
22. Full canonical install from GitHub → verify paperclip access
23. Edit config via paperclip → build payload → verify
24. Test SSH key resolution from User Secrets
25. Test flat file fallback for SSH keys
26. Test reinstall preserves config via agent_storage
27. Verify error messages in build UI
28. Bump version → build Docker → push Hub → push GitHub → clean install → verify

---

## 10. Documentation Rewrite Scope

| Document | Action |
|----------|--------|
| `documentation-wrapper/dolos/setup.md` | **Rewrite** — Flat-file naming, paperclip editing, User Secrets for SSH |
| `documentation-wrapper/dolos/encoder-setup.md` | **Rewrite** — No directories, filename references, User Secrets |
| `documentation-wrapper/dolos/build-parameters.md` | **Update** — Encoder dropdown reflects flat-file configs |
| `documentation-wrapper/dolos/troubleshooting.md` | **Update** — New error messages, missing secret troubleshooting |
| `README.md` | **Rewrite** — V2 architecture, paperclip-first config, User Secrets |
| `docs/10-decisions/*` | **Keep** — Historical context |

New documentation pages:
| New Document | Content |
|-------------|---------|
| `creating-encoders.md` | Copy PyEncoder → change prefix → update command → test |
| `shellcode-ack.md` | Reference profile for Liskit's encoder |
| `donut-encoder.md` | Reference profile for Donut converter |
| `ssh-key-setup.md` | Two paths: User Secrets (primary) + paperclip fallback |
| `windows-target-setup.md` | Run install script on target Windows machine |

---

## 11. Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SSH key storage | Mythic User Secrets (primary) + flat file fallback | Per-operator privacy, UI-managed, no host filesystem access needed |
| Config format | Flat files with naming convention | Enumerateable by filename, paperclip-editable, no directory traversal |
| Default encoder | PyEncoder for Windows (enabled) | Working out of box, needs only SSH creds |
| Install method | PowerShell script via winget | Legitimate, no evasion, standard Python install |
| Commercial tools | Documented with links, not shipped | Shellcode Ack, Donut — reference profiles only |
| Schema versioning | `"version": 2` in JSON | Forward compatibility |
| Config persistence | Hasura agent_storage sync | Paperclip edits survive reinstalls |
| Branch strategy | `feature/ui-managed-configs` from `master` | Clean branch, merge when stable |
| Version | v2.0.0 | Breaking change to config format |

---

*This plan is awaiting approval before implementation begins.*