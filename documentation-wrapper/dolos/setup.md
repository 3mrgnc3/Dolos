+++
title = "Setup"
weight = 10
+++

## SSH Configuration

Dolos uses SSH password-based authentication to connect to the external server.
All SSH configuration is stored in Mythic's `.env` file, not in build parameters.

<svg viewBox="0 0 700 300" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:700px;">
  <rect width="700" height="300" rx="12" fill="#1a1d23" stroke="#2a2f3a" stroke-width="1"/>
  <defs>
    <marker id="arr2" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#4a9eff"/>
    </marker>
  </defs>

  <!-- Dev machine -->
  <rect x="20" y="120" width="140" height="60" rx="8" fill="#1e2a3a" stroke="#4a9eff" stroke-width="2"/>
  <text x="90" y="148" font-family="system-ui" font-size="12" fill="#4a9eff" text-anchor="middle" font-weight="bold">Dev Machine</text>
  <text x="90" y="168" font-family="monospace" font-size="9" fill="#888" text-anchor="middle">mythic-cli install</text>

  <!-- Mythic server (Docker) -->
  <rect x="220" y="30" width="180" height="240" rx="8" fill="#2a1e3a" stroke="#a855f7" stroke-width="2"/>
  <text x="310" y="55" font-family="system-ui" font-size="12" fill="#a855f7" text-anchor="middle" font-weight="bold">Mythic (Docker)</text>

  <rect x="240" y="70" width="140" height="35" rx="4" fill="#352545" stroke="#a855f7" stroke-width="1"/>
  <text x="310" y="88" font-family="monospace" font-size="9" fill="#e0e0e0" text-anchor="middle">dolos container</text>
  <text x="310" y="100" font-family="monospace" font-size="8" fill="#888" text-anchor="middle">paramiko SSH</text>

  <rect x="240" y="120" width="140" height="35" rx="4" fill="#352545" stroke="#a855f7" stroke-width="1"/>
  <text x="310" y="138" font-family="monospace" font-size="9" fill="#e0e0e0" text-anchor="middle">mythic_graphql</text>
  <text x="310" y="150" font-family="monospace" font-size="8" fill="#888" text-anchor="middle">Hasura + RabbitMQ</text>

  <rect x="240" y="170" width="140" height="35" rx="4" fill="#352545" stroke="#a855f7" stroke-width="1"/>
  <text x="310" y="188" font-family="monospace" font-size="9" fill="#e0e0e0" text-anchor="middle">mythic_nginx</text>
  <text x="310" y="200" font-family="monospace" font-size="8" fill="#888" text-anchor="middle">:7443 HTTPS</text>

  <rect x="240" y="220" width="140" height="35" rx="4" fill="#1a2332" stroke="#f59e0b" stroke-width="1"/>
  <text x="310" y="238" font-family="monospace" font-size="8" fill="#f59e0b" text-anchor="middle">.env (DOLOS_SSH_*)</text>
  <text x="310" y="250" font-family="monospace" font-size="8" fill="#888" text-anchor="middle">DOLOS_REMOTE_COMMAND</text>

  <!-- Remote server -->
  <rect x="480" y="100" width="200" height="100" rx="8" fill="#1e3a2a" stroke="#22c55e" stroke-width="2"/>
  <text x="580" y="125" font-family="system-ui" font-size="12" fill="#22c55e" text-anchor="middle" font-weight="bold">Remote Server</text>
  <text x="580" y="145" font-family="monospace" font-size="9" fill="#e0e0e0" text-anchor="middle">Windows / Linux</text>
  <text x="580" y="160" font-family="monospace" font-size="8" fill="#888" text-anchor="middle">C:\tools\encoder.py</text>
  <text x="580" y="175" font-family="monospace" font-size="8" fill="#888" text-anchor="middle">C:\Windows\Temp\wd_*</text>

  <!-- Arrows -->
  <line x1="160" y1="145" x2="218" y2="88" stroke="#4a9eff" stroke-width="2" marker-end="url(#arr2)"/>
  <line x1="380" y1="88" x2="478" y2="140" stroke="#a855f7" stroke-width="2" marker-end="url(#arr2)"/>
  <text x="430" y="107" font-family="system-ui" font-size="9" fill="#a855f7">SSH/SFTP</text>
  <text x="430" y="155" font-family="system-ui" font-size="9" fill="#22c55e">result ↓</text>
  <line x1="478" y1="155" x2="382" y2="155" stroke="#22c55e" stroke-width="1.5" stroke-dasharray="4"/>
</svg>

### Setting Up Password Auth

1. Ensure the external server has SSH running and allows password authentication
2. Edit your Mythic `.env` file to set the SSH credentials:

```bash
DOLOS_SSH_HOST=172.28.0.3
DOLOS_SSH_PORT=22
DOLOS_SSH_USERNAME=mrgnc
DOLOS_SSH_PASSWORD=your_password_here
```

3. Reinstall the container to pick up the new environment variables:
```bash
cd /path/to/Mythic
./mythic-cli uninstall dolos
bash /path/to/Dolos/dev_tools/full_uninstall.sh
./mythic-cli install folder ../Dolos
```

### Verifying Connectivity

When you create a wrapper, Dolos automatically tests the SSH connection.
The build progress shows:
- ✅ SSH connectivity
- ✅ Password authentication
- ✅ SFTP write test (upload + delete a small test file)

If any step fails, you'll see ❌ with an error message and instructions.

## Environment Variables

All configuration is stored in Mythic's `.env` file. No build parameters for SSH.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DOLOS_SSH_HOST` | Yes | — | Hostname or IP of the external server |
| `DOLOS_SSH_PORT` | No | `22` | SSH port |
| `DOLOS_SSH_USERNAME` | Yes | — | SSH username |
| `DOLOS_SSH_PASSWORD` | Yes | — | SSH password for authentication |
| `DOLOS_REMOTE_COMMAND` | Yes | See below | JSON object of encoder commands |
| `DOLOS_TIMEOUT` | No | `300` | Default timeout in seconds |

### Adding Encoder Commands

The `DOLOS_REMOTE_COMMAND` variable is a JSON object where keys are display
labels and values are command strings with placeholders:

```bash
DOLOS_REMOTE_COMMAND={"PyEncoder_v1.0":"py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}","Donut_x64":"C:\\tools\\donut.exe -f 1 -i {workdir}\\{input} -o {workdir}\\{output}","ShellcodePack":"shellcodepack.exe -i {workdir}\\{input} -o {workdir}\\{output} -f exe --profile defender"}
```

**Important:** `{input}` and `{output}` resolve to **bare filenames only**
(no path). Use `{workdir}` to construct full paths. See [Placeholder Reference](placeholder-reference) for details.

To add a new encoder, edit `.env` and add a new key-value pair, then reinstall:
```bash
cd /path/to/Mythic
./mythic-cli uninstall dolos
bash /path/to/Dolos/dev_tools/full_uninstall.sh
./mythic-cli install folder ../Dolos
```

### Deploying the Built-in Tools

Dolos includes encoder tools that should be deployed to the remote server:

1. Copy `dev_tools/encoder/encoder.py` from the Dolos repository to
   `C:\tools\encoder.py` on the remote server
2. Copy `dev_tools/encoder/passthrough_encoder.py` to `C:\tools\passthrough_encoder.py`
   (pipeline test encoder — copies input to output unchanged)
3. Ensure `py.exe` (Python launcher) or `python.exe` is in the PATH
4. Ensure `csc.exe` is available at `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`
   (built into Windows)

### Connecting to a New Server

1. Update `DOLOS_SSH_HOST` (and other SSH vars if needed) in `.env`
2. Deploy the encoder to the new server (`C:\tools\encoder.py`)
3. Reinstall the container: `./mythic-cli uninstall dolos && bash dev_tools/full_uninstall.sh && ./mythic-cli install folder ../Dolos`
4. Create a wrapper — the connection test will verify the new server