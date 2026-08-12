# <img src="3mrgnc3_stricker_v2.png" width="120" height="120" alt="3mrgnc3 Sticker"></br> Dolos - The Craftsman of Lies

**Mythic wrapper payload type — encode shellcode on your own remote infrastructure with traditional scripting and tools.**

Dolos takes an existing built payload, transfers it to an external server over SSH, runs your encoder, and returns the result. It does no encoding itself — the remote encoder does all the work.

e.g connect to your own licenced copy of [Balliskit's ShellcodePack](https://balliskit.com/) tools and have all the processing and logs ingested automatically into Mythic's database.

---

## <img src="3mrgnc3_stricker_v2.png" width="120" height="120" alt="3mrgnc3 Sticker"></br> Quick Start

### 1. Install into Mythic

```bash
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

This pulls the pre-built Docker image from Docker Hub. No local build required.

To reinstall or update:

```bash
sudo ./mythic-cli uninstall dolos
sudo ./mythic-cli install github https://github.com/3mrgnc3/Dolos
```

### 2. Configure encoder profiles

Edit the `00_*.json` files inside the Dolos container via the Mythic paperclip UI.
Each file is a single encoder profile at `/Mythic/` root — flat-file, no subdirectories.

### 3. Add SSH credentials

In Mythic UI → Settings → Secrets, add your SSH private key as
`DOLOS_00_ENCODER_SSH_KEY`. The encoder profile references this secret by name.

### 4. Build

Mythic UI → **Create Wrapper** → select a payload → select Dolos → pick encoder → Build.

---

## v2 Architecture

Dolos v2 uses **flat-file configs** at `/Mythic/` root and **Mythic User Secrets** for SSH keys:

- **No `configs/` subdirectories** — every file is at `/Mythic/` root, visible in paperclip
- **No SSH key files on disk** — private keys come from Mythic's User Secrets API
- **No scaffolding** — the image ships with a sample encoder, operators edit via paperclip

### Config Directory

```
/Mythic/
├── 00_PyEncoder.json              ← encoder profile (paperclip-editable)
├── 00_Tool_pyencoder_encode.py    ← encoder script (paperclip-editable)
├── 00_Tool_pyencoder_install.ps1 ← install script (paperclip-editable)
├── main.py
└── dolos/
    ├── __init__.py
    ├── agent_functions/
    │   └── builder.py
    ├── config_loader.py
    ├── ssh_client.py
    └── hasura.py
```

---

## Changelog

- **v2.1.0** — Clean public release. Removed dev docs, cleaned up gitignore, updated documentation for v2.
- **v2.0.0** — Flat-file configs at `/Mythic/` root. Mythic User Secrets for SSH keys. Paperclip-editable. Fixed sync spam bug.
- **v1.0.9** — Author sticker, `rabbitmq_config.json` with correct Docker service names.
- **v1.0.8** — Rebuilt from clean source to verify all fixes.
- **v1.0.7** — Fix syntax error in main.py.
- **v1.0.6** — Remove custom env vars from config.json that caused Docker Compose warnings.
- **v1.0.5** — Remove harmful `rabbitmq_config.json`, fix local dev fallback.
- **v1.0.4** — Public release. Removed dev tools, config templates. Fresh Docker build.
- **v1.0.3** — MythicMeta-compliant repo structure, pre-built Docker Hub image, Apache 2.0 license.
- **v1.0.0** — Initial public release.