# Dolos

A Mythic 3rd-Party Service agent that transfers payload files to an external server over SSH, runs an encoder command, and returns the result to Mythic's Uploaded Files.

**It does NOT do any encoding itself.** All processing happens on the external server you control.

## Quick Start

1. Set SSH credentials in your Mythic `.env`:

```bash
DOLOS_SSH_HOST=172.28.0.3
DOLOS_SSH_PORT=22
DOLOS_SSH_USERNAME=mrgnc
DOLOS_SSH_PASSWORD=your_password
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

4. Create a payload: Mythic UI → Create Payload → Dolos → select file, pick encoder → Build.

## How It Works

```
Select file(s) in Mythic → SSH to external server → upload → run encoder → download result → store in Mythic
```

- Files come from Mythic's Uploaded Files (dropdowns, no manual upload)
- Encoder commands are configured in `.env` as JSON
- Random temp workdir per build, cleaned up after
- Result stored with metadata (file type, sizes, source file ID)

## Documentation

Full docs are served at `/docs/agents/dolos` in Mythic after install:

- **[Setup](documentation-payload/dolos/setup.md)** — SSH config, env vars, encoder deployment
- **[Build Parameters](documentation-payload/dolos/build-parameters.md)** — param reference
- **[Placeholder Reference](documentation-payload/dolos/placeholder-reference.md)** — `{workdir}`, `{input}`, `{output}`, `{file1}`
- **[Encoder Setup](documentation-payload/dolos/encoder-setup.md)** — C# cradle encoder, adding custom encoders
- **[Troubleshooting](documentation-payload/dolos/troubleshooting.md)** — common errors

## Development

- `CLAUDE.md` — how to work in this repo
- `PLAN.md` — active implementation plan
- `DECISIONS.md` — design decisions log

No `sudo` needed. Always uninstall before reinstalling.

## Mythic Compatibility

- Mythic >= 3.x
- `supported_os = ExternalEncoder` (appears under Services)