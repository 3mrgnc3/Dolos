# Dolos

A Mythic **wrapper** payload type that takes an existing built payload (selected via the native "Create Wrapper" flow), transfers it to an external server over SSH/SFTP, runs an encoder command, and returns the encoded result to Mythic's Uploaded Files.

**It does NOT do any encoding itself.** All processing happens on the external server you control. The wrapped payload's C2 is already embedded — no C2 profile selection needed.

## Quick Start

1. Set SSH credentials in your Mythic `.env` (key auth preferred, password as fallback — at least one required):

```bash
DOLOS_SSH_HOST=172.28.0.3
DOLOS_SSH_PORT=22
DOLOS_SSH_USERNAME=mrgnc
DOLOS_SSH_PASSWORD=your_password          # password auth (fallback)
DOLOS_SSH_PRIVATE_KEY=                     # optional: inline ed25519/RSA/ECDSA PEM for key auth
DOLOS_REMOTE_COMMAND={"PyEncoder_v1.0":"py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}"}
```

2. Deploy the encoder to your remote server:

Copy `dev_tools/encoder/encoder.py` to `C:\tools\encoder.py` on the Windows server. Requires Python (`py.exe`) and `csc.exe` (built into Windows).

3. Install Dolos:

```bash
cd /path/to/Mythic
./mythic-cli uninstall dolos
bash /path/to/Dolos/dev_tools/full_uninstall.sh
./mythic-cli install folder ../Dolos
```

4. Create a payload: Mythic UI → **Create Wrapper** → select an existing payload (e.g., Apollo) → select Dolos → pick encoder → Build. The wrapped payload's C2 is already embedded; no C2 profile step.

## How It Works

```
Create Wrapper → select payload → SSH to external server → upload → run encoder → download result → store in Mythic
```

- Wrapped payload bytes arrive natively via Mythic's wrapper flow (`self.wrapped_payload`)
- Encoder commands are configured in `.env` as JSON (static choices, no dynamic query)
- Random temp workdir per build, cleaned up after
- Result stored with magic-byte-aware filename + full SSH session log (JSON artifact)
- No callback creation — the wrapped agent (e.g., Apollo) callbacks, not Dolos

## Documentation

Full docs are served at `/docs/wrappers/dolos` in Mythic after install (source in `documentation-wrapper/dolos/`):

- **[Setup](documentation-wrapper/dolos/setup.md)** — SSH config, env vars, encoder deployment
- **[Build Parameters](documentation-wrapper/dolos/build-parameters.md)** — param reference
- **[Placeholder Reference](documentation-wrapper/dolos/placeholder-reference.md)** — `{workdir}`, `{input}`, `{output}`, `{file1}`
- **[Encoder Setup](documentation-wrapper/dolos/encoder-setup.md)** — C# cradle encoder, adding custom encoders
- **[Troubleshooting](documentation-wrapper/dolos/troubleshooting.md)** — common errors

## Development

- `CLAUDE.md` — how to work in this repo
- `PLAN.md` — active implementation plan
- `DECISIONS.md` — design decisions log

No `sudo` needed. Always uninstall before reinstalling.

## Mythic Compatibility

- Mythic >= 3.x
- Wrapper payload type (`wrapper=True`, `agent_type=AgentType.Wrapper`) — appears under **Create Wrapper**
- `supported_os = [SupportedOS.Windows]` (wrapper outputs Windows EXEs)
- `.NET Framework 4.x` required on target (standard on Win10/11)