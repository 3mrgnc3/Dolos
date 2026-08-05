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

- **Zero additional installs** — `csc.exe` ships with Windows (.NET Framework 4)
- **Guaranteed valid PE** — Microsoft's own compiler produces the output
- **Large payload support** — Uses `.resources` embedding (not base64 string literals)
  to avoid csc.exe's CS0013/CS1647 errors on payloads >1MB
- **x64 output** — `/platform:x64` for 64-bit shellcode
- **CreateThread execution** — v2.3 uses `CreateThread` instead of `GetDelegateForFunctionPointer`,
  which avoids CLR-managed transitions that interfered with some shellcode (notably
  Go-compiled agents like Merlin)

### Requirements on Remote Server

1. **Python** — `py.exe` (Python launcher) or `python.exe` in PATH
2. **csc.exe** — Available at `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`
3. **.NET Framework 4.x** — Required on the target machine (standard on Windows 10/11)

### Deployment

```powershell
# Copy the encoder to the remote server
scp dev_tools/encoder/encoder.py mrgnc@172.28.0.3:C:/tools/encoder.py

# Verify Python is available
py --version

# Verify csc.exe is available
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /?
```

### Default .env Configuration

```bash
DOLOS_REMOTE_COMMAND={"PyEncoder_v1.0":"py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}"}
```

## Adding Custom Encoder Commands

Encoder commands are stored in `DOLOS_REMOTE_COMMAND` as a JSON object.
Each key-value pair defines one encoder:

- **Key** = display label shown in the Encoder dropdown
- **Value** = full command string with placeholders

### Example Configurations

```bash
DOLOS_REMOTE_COMMAND={"PyEncoder_v1.0":"py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}","Donut_x64":"C:\\tools\\donut.exe -f 1 -i {workdir}\\{input} -o {workdir}\\{output}","Passthrough":"py.exe C:\\tools\\passthrough_encoder.py {workdir}\\{input} {workdir}\\{output}"}
```

- **PyEncoder_v1.0** — Built-in C# cradle encoder (recommended)
- **Donut_x64** — Donut shellcode packer (EXE/DLL → shellcode)
- **Passthrough** — Copies input to output unchanged (for pipeline testing)

### Adding a New Encoder

1. Install the encoder on the remote server (e.g., `C:\tools\new_encoder.exe`)
2. Edit `/path/to/Mythic/.env`
3. Add a new key-value pair to the `DOLOS_REMOTE_COMMAND` JSON
4. Reinstall the Dolos container
5. The new encoder will appear in the Encoder dropdown

### JSON Escaping in .env

- Use double backslashes for Windows paths: `C:\\tools\\encoder.exe`
- Keep the entire JSON on one line
- No spaces around the `=` sign

### Success/Failure Detection

Dolos checks for success and failure strings in the encoder's stdout:

- **Success String** (default: `ENCODING_SUCCESS`) — If found in stdout, encoding is confirmed
- **Fail String** (default: `ENCODING_FAILED`) — If found in stdout/stderr, encoding is confirmed failed

Your encoder should print one of these to stdout so Dolos can detect the result:

```python
# Success:
print("ENCODING_SUCCESS")

# Failure:
print("ENCODING_FAILED: Invalid input format")
```

## Example: BallisKit ShellcodePack

> **Note:** ShellcodePack is a **third-party commercial product** by BallisKit SAS.
> It is not included with Dolos and requires a separate license (€875/year).
> This section demonstrates how to integrate a proprietary encoder.

[ShellcodePack](https://balliskit.com/products/shellcodepack) is a professional
shellcode weaponization tool that converts shellcode into deployment-ready payloads
with EDR evasion, indirect syscalls, AMSI bypass, and multiple output formats
(.exe, .dll, .bin, .c, .py, .asm, .cpl, .xll, .scr).

### Key Features

| Category | Capabilities |
|----------|--------------|
| Input | .bin, .exe (including Go and Rust), .dll, .NET assemblies, .asm, .c |
| Output | .exe (native or .NET), .dll, .bin, .c, .py, .asm, .cpl, .xll, .scr |
| Evasion | Indirect syscalls, callstack spoofing, ETW patching, AMSI bypass, DLL unhooking |
| Delivery | DLL proxying/sideloading, Windows Service generation, TCP/HTTPS stagers |
| Guardrails | Domain, username, date, file-based execution conditions |

### Integration with Dolos

1. **Install ShellcodePack CLI** on the remote server (e.g., `C:\tools\shellcodepack.exe`)
2. **Add to `DOLOS_REMOTE_COMMAND`** in `.env`:

```bash
DOLOS_REMOTE_COMMAND={"PyEncoder_v1.0":"py.exe C:\\tools\\encoder.py {workdir}\\{input} {workdir}\\{output}","ShellcodePack_EXE":"C:\\tools\\shellcodepack.exe -i {workdir}\\{input} -o {workdir}\\{output} -f exe --profile defender","ShellcodePack_DLL":"C:\\tools\\shellcodepack.exe -i {workdir}\\{input} -o {workdir}\\{output} -f dll --profile defender"}
```

3. **Reinstall** the Dolos container. Two new options appear in the Encoder dropdown:
   - **ShellcodePack_EXE** — Produce a standalone EXE with Defender evasion
   - **ShellcodePack_DLL** — Produce a reflective DLL with Defender evasion

4. **Success string**: ShellcodePack prints `ENCODING_SUCCESS` by default when it
   completes. If your version uses a different output format, adjust the
   **Success String** build parameter accordingly.

### Why This Works

Dolos doesn't know or care what the encoder actually is. It just:
1. Uploads the wrapped payload to the remote workdir
2. Runs whatever command you configured
3. Downloads the result file (`wd_out.bin`)
4. Checks stdout for success/failure strings
5. Returns the result to Mythic

Any command-line tool that takes an input file and produces an output file can be
integrated this way. See [Placeholder Reference](placeholder-reference) for the
full placeholder syntax.