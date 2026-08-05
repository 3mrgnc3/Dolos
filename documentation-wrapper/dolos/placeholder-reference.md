+++
title = "Placeholder Reference"
weight = 30
+++

## Command Placeholder Reference

The encoder command string supports these placeholders. Dolos resolves them
to actual values before executing the command on the remote server.

<svg viewBox="0 0 600 260" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:600px;">
  <rect width="600" height="260" rx="8" fill="#1a1d23" stroke="#2a2f3a"/>
  <text x="300" y="25" font-family="system-ui" font-size="14" fill="#4a9eff" text-anchor="middle" font-weight="bold">Placeholder Resolution</text>

  <rect x="20" y="45" width="260" height="200" rx="6" fill="#252d3d" stroke="#a855f7"/>
  <text x="150" y="68" font-family="system-ui" font-size="11" fill="#a855f7" text-anchor="middle" font-weight="bold">Template (in .env)</text>
  <text x="35" y="95" font-family="monospace" font-size="10" fill="#e0e0e0">py.exe C:\tools\encoder.py</text>
  <text x="35" y="112" font-family="monospace" font-size="10" fill="#e0e0e0">  <tspan fill="#f59e0b">{workdir}</tspan>\<tspan fill="#22c55e">{input}</tspan></text>
  <text x="35" y="129" font-family="monospace" font-size="10" fill="#e0e0e0">  <tspan fill="#f59e0b">{workdir}</tspan>\<tspan fill="#4a9eff">{output}</tspan></text>

  <rect x="320" y="45" width="260" height="200" rx="6" fill="#252d3d" stroke="#22c55e"/>
  <text x="450" y="68" font-family="system-ui" font-size="11" fill="#22c55e" text-anchor="middle" font-weight="bold">Resolved (on remote)</text>
  <text x="335" y="95" font-family="monospace" font-size="10" fill="#e0e0e0">py.exe C:\tools\encoder.py</text>
  <text x="335" y="112" font-family="monospace" font-size="10" fill="#e0e0e0">  C:\Windows\Temp\<tspan fill="#f59e0b">wd_a3f7kx</tspan>\<tspan fill="#22c55e">wd_in.bin</tspan></text>
  <text x="335" y="129" font-family="monospace" font-size="10" fill="#e0e0e0">  C:\Windows\Temp\<tspan fill="#f59e0b">wd_a3f7kx</tspan>\<tspan fill="#4a9eff">wd_out.bin</tspan></text>

  <!-- Arrow -->
  <line x1="280" y1="130" x2="320" y2="130" stroke="#888" stroke-width="2"/>
  <text x="300" y="120" font-family="system-ui" font-size="9" fill="#888" text-anchor="middle">resolve</text>

  <!-- Legend -->
  <rect x="20" y="150" width="260" height="90" rx="4" fill="#1a2332" stroke="#444"/>
  <text x="35" y="170" font-family="monospace" font-size="10" fill="#f59e0b">{workdir}</text>
  <text x="155" y="170" font-family="system-ui" font-size="10" fill="#888">→ Full path (OS slashes)</text>
  <text x="35" y="188" font-family="monospace" font-size="10" fill="#22c55e">{input}</text>
  <text x="155" y="188" font-family="system-ui" font-size="10" fill="#888">→ wd_in.bin (bare name)</text>
  <text x="35" y="206" font-family="monospace" font-size="10" fill="#4a9eff">{output}</text>
  <text x="155" y="206" font-family="system-ui" font-size="10" fill="#888">→ wd_out.bin (bare name)</text>
  <text x="35" y="224" font-family="monospace" font-size="10" fill="#e0e0e0">{workdir}</text>
  <text x="155" y="224" font-family="system-ui" font-size="10" fill="#888">→ \ on Windows, / on Linux</text>
</svg>

**Important:** `{input}` and `{output}` resolve to **bare filenames only**
(no directory path). Use `{workdir}` to construct full paths.

| Placeholder | Description | Example Value |
|---|---|---|
| `{workdir}` | Full path to the temporary working directory (OS-appropriate slashes) | `C:\Windows\Temp\wd_a3f7kx` on Windows, `/tmp/wd_a3f7kx` on Linux |
| `{input}` | Filename of the wrapped payload (bare name, no path) | `wd_in.bin` |
| `{output}` | Filename for the result output (bare name, no path) | `wd_out.bin` |

### How It Works

1. Dolos generates a random 6-character workdir name (e.g. `wd_a3f7kx`)
2. The working directory is created on the remote server under the system temp path:
   - Windows: `C:\Windows\Temp\wd_a3f7kx\`
   - Linux: `/tmp/wd_a3f7kx/`
3. The wrapped payload is uploaded as `wd_in.bin` in that directory
4. The encoder command is run with all placeholders replaced
5. Dolos downloads the output file named `wd_out.bin` from the workdir
6. The entire working directory is deleted from the remote server

### Example Commands

**Python encoder on Windows (recommended):**
```
py.exe C:\tools\encoder.py {workdir}\{input} {workdir}\{output}
```
Resolves to:
```
py.exe C:\tools\encoder.py C:\Windows\Temp\wd_a3f7kx\wd_in.bin C:\Windows\Temp\wd_a3f7kx\wd_out.bin
```

**Donut shellcode packer:**
```
C:\tools\donut.exe -f 1 -i {workdir}\{input} -o {workdir}\{output}
```

**BallisKit ShellcodePack:**
```
C:\tools\shellcodepack.exe -i {workdir}\{input} -o {workdir}\{output} -f exe --profile defender
```

**Linux encoder:**
```
/opt/tools/encoder.py /tmp/{workdir}/{input} /tmp/{workdir}/{output}
```

### OS Path Handling

- **SFTP operations** (upload/download) always use forward slashes (`/`) regardless of OS
- **Command execution** uses OS-appropriate slashes:
  - Windows → backslashes in `{workdir}` (e.g. `C:\Windows\Temp\wd_a3f7kx`)
  - Linux → forward slashes in `{workdir}` (e.g. `/tmp/wd_a3f7kx`)
- Dolos auto-detects the remote OS (runs `ver` first, then `uname`)