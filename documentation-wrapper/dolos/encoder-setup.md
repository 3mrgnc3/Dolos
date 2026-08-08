+++
title = "Encoder Setup"
weight = 40
+++

## Built-in Encoder v2.3 (C# Cradle)

Dolos includes a Python-based encoder (`dev_tools/encoder/encoder.py` in the repo)
that converts raw shellcode into standalone Windows PE executables using C# and `csc.exe`.

<svg viewBox="0 0 700 220" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:700px;">
  <rect width="700" height="220" rx="12" fill="#1a1d23" stroke="#2a2f3a" stroke-width="1"/>
  <defs>
    <marker id="arr3" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#22c55e"/>
    </marker>
  </defs>

  <!-- Input -->
  <rect x="20" y="80" width="130" height="60" rx="6" fill="#1e2a3a" stroke="#4a9eff" stroke-width="2"/>
  <text x="85" y="105" font-family="system-ui" font-size="12" fill="#4a9eff" text-anchor="middle" font-weight="bold">Input</text>
  <text x="85" y="125" font-family="monospace" font-size="10" fill="#888" text-anchor="middle">shellcode.bin</text>

  <!-- Encoder -->
  <rect x="210" y="40" width="280" height="140" rx="8" fill="#252d3d" stroke="#a855f7" stroke-width="2"/>
  <text x="350" y="60" font-family="system-ui" font-size="13" fill="#a855f7" text-anchor="middle" font-weight="bold">encoder.py (v2.3)</text>
  <text x="350" y="85" font-family="monospace" font-size="10" fill="#e0e0e0" text-anchor="middle">1. Detect input type (PE or shellcode)</text>
  <text x="350" y="102" font-family="monospace" font-size="10" fill="#e0e0e0" text-anchor="middle">2. Generate C# source + .resources</text>
  <text x="350" y="119" font-family="monospace" font-size="10" fill="#e0e0e0" text-anchor="middle">3. Compile with csc.exe /platform:x64</text>
  <text x="350" y="136" font-family="monospace" font-size="10" fill="#e0e0e0" text-anchor="middle">4. Print ENCODING_SUCCESS:type→arch</text>
  <text x="350" y="170" font-family="monospace" font-size="9" fill="#888" text-anchor="middle">CreateThread runner + .resources embedding</text>

  <!-- Output -->
  <rect x="560" y="80" width="130" height="60" rx="6" fill="#1e3a2a" stroke="#22c55e" stroke-width="2"/>
  <text x="625" y="105" font-family="system-ui" font-size="12" fill="#22c55e" text-anchor="middle" font-weight="bold">Output</text>
  <text x="625" y="125" font-family="monospace" font-size="10" fill="#888" text-anchor="middle">payload.exe</text>

  <!-- Arrows -->
  <line x1="150" y1="110" x2="208" y2="110" stroke="#4a9eff" stroke-width="2" marker-end="url(#arr3)"/>
  <line x1="490" y1="110" x2="558" y2="110" stroke="#22c55e" stroke-width="2" marker-end="url(#arr3)"/>

  <!-- PE pass-through note -->
  <rect x="210" y="160" width="280" height="25" rx="4" fill="#2a2a1e" stroke="#f59e0b" stroke-width="1"/>
  <text x="350" y="177" font-family="system-ui" font-size="9" fill="#f59e0b" text-anchor="middle">⚠ PE input → passed through unchanged (no recompile)</text>
</svg>

### Why C# + csc.exe?

Previous versions used a hand-rolled PE32+ builder that produced EXEs Windows rejected.
The C# approach uses Microsoft's own compiler, guaranteeing valid PE output:

- **Zero additional installs** - `csc.exe` ships with Windows (.NET Framework 4)
- **Guaranteed valid PE** - Microsoft's own compiler produces the output
- **Large payload support** - Uses `.resources` embedding (not base64 string literals)
- **x64 output** - `/platform:x64` for 64-bit shellcode
- **CreateThread execution** - v2.3 uses `CreateThread` instead of `GetDelegateForFunctionPointer`

### Requirements on Remote Server

1. **Python** - `py.exe` (Python launcher) or `python.exe` in PATH
2. **csc.exe** - Available at `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`
3. **.NET Framework 4.x** - Required on the target machine (standard on Windows 10/11)

### Deployment

```powershell
# Copy the encoder to the remote server
scp dev_tools/encoder/encoder.py operator@192.168.1.100:C:/tools/encoder.py

# Verify Python is available
py --version

# Verify csc.exe is available
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /?
```

### Minimal Encoder Profile

The auto-scaffolded default profile is a good starting point:

```json
{
    "index": 0,
    "label": "PyEncoder_v1",
    "command": "py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}",
    "ssh_server": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "operator",
        "password": "",
        "keys": {"enabled": false, "path": ""}
    },
    "timeout": 300,
    "bypass_profiles": ""
}
```

Edit the `ssh_server` section with your server's credentials and reinstall.

## Adding Custom Encoders

Each encoder gets its own directory under `configs/encoders/`. The `label` field
is what appears in the Mythic UI dropdown.

### Simple Encoder (Single Command)

```json
{
    "index": 1,
    "label": "Donut_x64",
    "enabled": true,
    "command": "C:\\tools\\donut.exe -f 1 -i {workdir}\\{input} -o {workdir}\\{output}",
    "ssh_server": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "operator",
        "password": "your_password",
        "keys": {"enabled": false, "path": ""}
    },
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": false,
    "toolset": "",
    "bypass_profiles": ""
}
```

### Encoder with Key Auth

```json
{
    "index": 2,
    "label": "PyEncoder_v1",
    "enabled": true,
    "command": "py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}",
    "ssh_server": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "operator",
        "password": "",
        "keys": {
            "enabled": true,
            "path": "../../ssh_keys/tiny11/id_ed25519"
        }
    },
    "timeout": 300,
    "bypass_profiles": ""
}
```

### Encoder with Bypass Profiles

For encoders that support EDR evasion profiles (e.g., ShellcodePack):

```json
{
    "index": 3,
    "label": "ShellcodePack_v2.6",
    "enabled": true,
    "command": "C:\\tools\\shellcodepack.exe -i {workdir}\\{input} -G {workdir}\\{output} --profile C:\\tools\\profiles\\{bypass_profile}.json",
    "ssh_server": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "operator",
        "password": "",
        "keys": {"enabled": true, "path": "../id_ed25519"}
    },
    "timeout": 600,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "toolset": "balliskit",
    "bypass_profiles": "../bypass_profiles"
}
```

The `bypass_profiles` path is relative to the `encoder_profile.json` file.
Place bypass profile JSON files in the referenced directory:

```
configs/encoders/balliskit/
├── macropack/
│   └── encoder_profile.json          ← points to "../bypass_profiles"
├── shellcodepack/
│   └── encoder_profile.json          ← points to "../bypass_profiles"
├── bypass_profiles/
│   ├── cortex_bypass_profile.json
│   ├── cs_bypass_profile.json
│   ├── kaspersky_bypass_profile.json
│   └── s1_bypass_profile.json
└── id_ed25519                         ← shared SSH key
```

When an encoder has bypass profiles, the **Bypass Profile** dropdown appears
in the build dialog with entries like **"Balliskit / Cortex Bypass"**.

### Per-Encoder Timeout

Each encoder profile has its own `timeout` field (in seconds). This is useful
for slow servers or complex encoders that take longer to complete:

```json
{
    "label": "ShellcodePack_v2.6",
    "timeout": 600,
    ...
}
```

The `Timeout` build parameter (default: 0) overrides the profile's timeout
when set to a non-zero value.

## Directory Layout for Multiple Encoders on the Same Server

If multiple encoders share the same SSH server, you can organize them under
a common directory with a shared SSH key:

```
configs/encoders/balliskit/
├── macropack/
│   └── encoder_profile.json     ← host: 192.168.1.100, keys.path: ../../ssh_keys/tiny11/id_ed25519
├── shellcodepack/
│   └── encoder_profile.json     ← host: 192.168.1.100, keys.path: ../../ssh_keys/tiny11/id_ed25519
└── bypass_profiles/
    └── *.json
```

Or place the key alongside the profiles:

```
configs/encoders/balliskit/
├── macropack/
│   └── encoder_profile.json     ← keys.path: ../id_ed25519
├── id_ed25519                   ← private key
└── id_ed25519.pub               ← public key (optional, not used for auth)
```

### Success/Failure Detection

Dolos checks for success and failure strings in the encoder's stdout. These are configured per-encoder in `encoder_profile.json` - not in the build UI:

- **`success_string`** (default: `ENCODING_SUCCESS`) - If found in stdout, encoding is confirmed
- **`fail_string`** (default: `ENCODING_FAILED`) - If found in stdout/stderr, encoding is confirmed failed

Your encoder should print one of these to stdout:

```python
# Success:
print("ENCODING_SUCCESS")

# Failure:
print("ENCODING_FAILED: Invalid input format")
```

### Tool Auto-Installation

When `install_tools` is `true` and `toolset` is set, Dolos automatically installs required tools on the remote server before running the encoder command:

1. Detects the remote OS (Windows or Linux)
2. Uploads files from `configs/tools/{toolset}/` to the remote workdir
3. Runs `install_windows.ps1` or `install_linux.sh`
4. If the script fails → build fails with a clear error message

Scripts are **idempotent** - if tools are already present, they exit 0 immediately.

Example toolset directory:

```
configs/tools/pyencoderv1/
├── install_windows.ps1    ← installs Python via winget
└── install_linux.sh       ← installs Python via apt
```

If `install_tools` is `false` or `toolset` is empty, Dolos skips tool installation entirely. You can also add any additional files (scripts, configs) alongside the install scripts - they'll be uploaded to the remote workdir before the script runs.

Toolset directories that only have a `SETUP.md` (like `donut_x64` and `balliskit`) are placeholders - they contain instructions for operators to set up tools manually or connect to a server where they're already installed.