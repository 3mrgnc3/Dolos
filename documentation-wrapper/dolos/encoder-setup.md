+++
title = "Encoder Setup"
weight = 15
+++

## Encoder-agnostic by Design

Dolos is **encoder-agnostic** — it supports all shellcode and processed payload types.
It connects to your own pre-configured remote SSH server and runs whatever encoding
command you configure. The output format depends entirely on your encoder:
EXE, DLL, shellcode bin, PowerShell script, HTA, or anything else your tool produces.

The included PyEncoder is a **starting example** to demonstrate the capabilities.
For real operations, connect to your own licensed copy of
[Balliskit's ShellcodePack](https://balliskit.com/) or any other tool.

## Included Encoder: PyEncoder

Dolos ships with PyEncoder — a Python-based encoder that uses the Windows C# compiler
(`csc.exe`) to create a .NET cradle that loads and executes shellcode. It's a working
example you can use as-is or as a template for your own encoders.

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

- **Zero additional installs** — `csc.exe` ships with Windows (.NET Framework 4)
- **Guaranteed valid PE** — Microsoft's own compiler produces the output
- **Large payload support** — Uses `.resources` embedding (not base64 string literals)
- **x64 output** — `/platform:x64` for 64-bit shellcode
- **CreateThread execution** — v2.3 uses `CreateThread` instead of `GetDelegateForFunctionPointer`

### Deploying the PyEncoder

Copy `00_Tool_pyencoder_encode.py` to `C:\tools\dolos\encoder.py` on your remote server:

```powershell
scp 00_Tool_pyencoder_encode.py operator@192.168.1.100:C:/tools/dolos/encoder.py
```

Requires Python (`py.exe`) and `csc.exe` (built into Windows). If `install_tools` is `true`,
Dolos will attempt to install Python automatically using `00_Tool_pyencoder_install.ps1`.

## Balliskit ShellcodePack & MacroPack

Dolos works with [Balliskit's](https://balliskit.com/) commercial tools — ShellcodePack
and MacroPack. These are **proprietary** and not included, but configuring Dolos to use them
is straightforward.

### ShellcodePack Encoder Profile

Create `01_ShellcodePack.json` in `/Mythic/` via the paperclip UI:

```json
{
    "version": 2,
    "label": "ShellcodePack",
    "enabled": true,
    "command": "C:\\tools\\shellcodepack.exe -i {workdir}\\{input} -o {workdir}\\{output} --profile C:\\tools\\profiles\\{bypass_profile}.json",
    "ssh_host": "192.168.1.100",
    "ssh_port": 22,
    "ssh_username": "operator",
    "ssh_password": "",
    "ssh_key_enabled": true,
    "ssh_key_secret": "DOLOS_01_ENCODER_SSH_KEY",
    "timeout": 600,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": true,
    "bypass_refs": ["01_Bypass_AMSI", "01_Bypass_ETW"],
    "notes": "Balliskit ShellcodePack - licensed tool. Contact balliskit.com for licenses."
}
```

### Bypass Profiles for ShellcodePack

Create bypass profile files in `/Mythic/` — these appear as a dropdown in the Mythic build dialog:

`01_Bypass_AMSI.json`:
```json
{
    "name": "AMSI Bypass",
    "technique": "amsi",
    "description": "Bypass AMSI patching before shellcode execution"
}
```

`01_Bypass_ETW.json`:
```json
{
    "name": "ETW Patch",
    "technique": "etw",
    "description": "Patch ETW event tracing before shellcode execution"
}
```

### MacroPack Encoder Profile

Create `02_MacroPack.json`:

```json
{
    "version": 2,
    "label": "MacroPack",
    "enabled": true,
    "command": "C:\\tools\\macropack.exe -i {workdir}\\{input} -o {workdir}\\{output} --type vba",
    "ssh_host": "192.168.1.100",
    "ssh_port": 22,
    "ssh_username": "operator",
    "ssh_password": "",
    "ssh_key_enabled": true,
    "ssh_key_secret": "DOLOS_02_ENCODER_SSH_KEY",
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": false,
    "bypass_refs": [],
    "notes": "Balliskit MacroPack - licensed tool. Contact balliskit.com for licenses."
}
```

## Adding Custom Encoders

Each encoder gets its own `NN_Label.json` file in `/Mythic/` where `NN` is a group number.
The `NN_` prefix groups the encoder profile with its matching tool files. The `label` field
is what appears in the Mythic UI dropdown.

### Simple Encoder (Donut)

```json
{
    "version": 2,
    "label": "Donut_x64",
    "enabled": true,
    "command": "C:\\tools\\donut.exe -f 1 -i {workdir}\\{input} -o {workdir}\\{output}",
    "ssh_host": "192.168.1.100",
    "ssh_port": 22,
    "ssh_username": "operator",
    "ssh_password": "your_password",
    "ssh_key_enabled": false,
    "ssh_key_secret": "",
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": false,
    "bypass_refs": [],
    "notes": "Donut shellcode-to-EXE converter"
}
```

### Encoder with Key Auth

```json
{
    "version": 2,
    "label": "Custom_Encoder",
    "enabled": true,
    "command": "/usr/local/bin/custom_encoder {workdir}/{input} {workdir}/{output}",
    "ssh_host": "linux-server.example.com",
    "ssh_port": 22,
    "ssh_username": "operator",
    "ssh_password": "",
    "ssh_key_enabled": true,
    "ssh_key_secret": "DOLOS_03_ENCODER_SSH_KEY",
    "timeout": 300,
    "success_string": "ENCODING_SUCCESS",
    "fail_string": "ENCODING_FAILED",
    "install_tools": false,
    "bypass_refs": [],
    "notes": "Linux-based custom encoder with SSH key auth"
}
```

### Multiple Encoders on the Same Server

If multiple encoders share the same SSH server, use the same `ssh_host` and `ssh_key_secret`
across profiles. Each encoder is a separate `NN_Label.json` file:

```
/Mythic/
├── 01_ShellcodePack.json              ← Balliskit ShellcodePack profile
├── 01_Tool_shellcodepack_install.ps1  ← ShellcodePack install script
├── 01_Bypass_AMSI.json                ← AMSI bypass profile for ShellcodePack
├── 01_Bypass_ETW.json                 ← ETW bypass profile for ShellcodePack
├── 02_MacroPack.json                  ← Balliskit MacroPack profile
├── 02_Tool_macropack_install.ps1      ← MacroPack install script
└── 03_Donut.json                      ← Simple donut converter
```

### Encoder Command Template Placeholders

| Placeholder | Description |
|-------------|-------------|
| `{workdir}` | Temporary directory on the remote server (created per build, cleaned up after) |
| `{input}` | Filename of the uploaded payload in the workdir |
| `{output}` | Desired output filename in the workdir |
| `{bypass_profile}` | Selected bypass profile name (stem of the JSON filename, no extension) |

### Per-Encoder Timeout

Each encoder profile has its own `timeout` field (in seconds). This is useful for slow
servers or complex encoders like ShellcodePack that take longer to complete. The
**Timeout** build parameter (default: 300) overrides the profile's timeout when set
to a non-zero value.