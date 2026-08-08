+++
title = "Dolos"
chapter = true
weight = 100
+++

![logo](dolos.svg?width=100px)

## Dolos 🎭 The Craftsman of Lies

Dolos is a **Mythic wrapper payload type** that transforms an existing built payload
via an external SSH-connected server. You select a payload, choose an encoder profile,
and Dolos transfers it to the remote server, runs the encoder, and brings the
result back - all over SSH/SFTP.

<svg viewBox="0 0 800 380" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:800px;">
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#4a9eff"/>
    </marker>
    <style>
      .box { rx: 8; ry: 8; stroke-width: 2; }
      .label { font-family: system-ui, sans-serif; font-size: 13px; fill: #e0e0e0; text-anchor: middle; }
      .title { font-family: system-ui, sans-serif; font-size: 11px; fill: #888; text-anchor: middle; }
      .step { font-family: monospace; font-size: 10px; fill: #6a6; }
    </style>
  </defs>

  <!-- Background -->
  <rect width="800" height="380" rx="12" fill="#1a1d23" stroke="#2a2f3a" stroke-width="1"/>

  <!-- Mythic Server -->
  <rect x="30" y="40" width="200" height="140" class="box" fill="#1e2a3a" stroke="#4a9eff"/>
  <text x="130" y="65" class="label" font-weight="bold" fill="#4a9eff">Mythic Server</text>
  <rect x="50" y="80" width="160" height="30" rx="4" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="130" y="100" class="label" font-size="11">Create Wrapper → Dolos</text>
  <rect x="50" y="120" width="160" height="30" rx="4" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="130" y="140" class="label" font-size="11">Build Result (EXE/DLL)</text>

  <!-- Dolos Container -->
  <rect x="280" y="40" width="220" height="140" class="box" fill="#2a1e3a" stroke="#a855f7"/>
  <text x="390" y="65" class="label" font-weight="bold" fill="#a855f7">Dolos Container</text>
  <text x="390" y="90" class="step">① SSH connect + auth</text>
  <text x="390" y="105" class="step">② SFTP upload payload</text>
  <text x="390" y="120" class="step">③ Install tools (if configured)</text>
  <text x="390" y="135" class="step">④ SSH exec encoder</text>
  <text x="390" y="150" class="step">⑤ SFTP download result</text>
  <text x="390" y="165" class="step">⑥ SFTP cleanup workdir</text>

  <!-- Remote Server -->
  <rect x="550" y="40" width="220" height="140" class="box" fill="#1e3a2a" stroke="#22c55e"/>
  <text x="660" y="65" class="label" font-weight="bold" fill="#22c55e">Remote Server</text>
  <rect x="570" y="80" width="180" height="28" rx="4" fill="#253d2d" stroke="#22c55e" stroke-width="1"/>
  <text x="660" y="99" class="label" font-size="10">C:\tools\encoder.py</text>
  <rect x="570" y="115" width="180" height="28" rx="4" fill="#253d2d" stroke="#22c55e" stroke-width="1"/>
  <text x="660" y="134" class="label" font-size="10">C:\Windows\Temp\wd_XXXXX\</text>
  <rect x="570" y="150" width="180" height="22" rx="4" fill="#253d2d" stroke="#22c55e" stroke-width="1"/>
  <text x="660" y="165" class="label" font-size="10">csc.exe / donut.exe / etc.</text>

  <!-- Arrows -->
  <line x1="230" y1="110" x2="275" y2="110" stroke="#4a9eff" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="252" y="104" class="title">payload</text>

  <line x1="500" y1="95" x2="545" y2="95" stroke="#a855f7" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="522" y="89" class="title" fill="#a855f7">② upload</text>

  <line x1="545" y1="130" x2="500" y2="130" stroke="#22c55e" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="522" y="146" class="title" fill="#22c55e">④ download</text>

  <line x1="275" y1="160" x2="230" y2="160" stroke="#4a9eff" stroke-width="2" marker-end="url(#arrowhead)"/>
  <text x="252" y="175" class="title">result + log</text>

  <!-- Session Log Box -->
  <rect x="30" y="220" width="740" height="55" rx="8" fill="#1a2332" stroke="#f59e0b" stroke-width="1"/>
  <text x="400" y="242" class="label" fill="#f59e0b" font-weight="bold">📄 Session Log Artifact</text>
  <text x="400" y="260" class="label" font-size="11" fill="#888">payload_name.session.json - full timestamped log of every SSH/SFTP event, stdout/stderr, exit codes</text>

  <!-- Key Features -->
  <rect x="30" y="295" width="740" height="70" rx="8" fill="#1a2332" stroke="#444" stroke-width="1"/>
  <text x="130" y="322" class="label" fill="#4a9eff" font-weight="bold">Wrapper Flow</text>
  <text x="130" y="340" class="title" font-size="10">No C2 selection</text>
  <text x="130" y="355" class="title" font-size="10">Native payload picker</text>
  <text x="340" y="322" class="label" fill="#a855f7" font-weight="bold">Encoders</text>
  <text x="340" y="340" class="title" font-size="10">Per-profile SSH config</text>
  <text x="340" y="355" class="title" font-size="10">Bypass profiles support</text>
  <text x="560" y="322" class="label" fill="#22c55e" font-weight="bold">Session Log</text>
  <text x="560" y="340" class="title" font-size="10">JSON artifact per build</text>
  <text x="560" y="355" class="title" font-size="10">Forensic timestamps</text>
</svg>

**Current version: v1.0.5**

### Quick Start

1. **Configure encoder profiles** - Edit `configs/encoders/*/encoder_profile.json` with
   your SSH server details and encoder command templates (see [Setup](setup))
2. **Deploy encoder tools** - Copy `encoder.py` to `C:\tools\` on the remote server
3. **SSH keys** (optional) - Place private keys in `configs/ssh_keys/` and reference them
   from encoder profiles
4. **Install Dolos** - `mythic-cli install folder ../Dolos` (see [Setup](setup))
5. **Create a payload** - Build any payload (e.g., Apollo) with its C2 profile
6. **Create a wrapper** - Go to Create Wrapper → Dolos → select the payload → choose encoder → Build
7. **Download the result** - Get your wrapped EXE/DLL with full session log

### How It Works

Dolos is a **wrapper**, not a normal payload. It appears under **Create Wrapper** (not Create Payload)
in Mythic's UI. The wrapped payload's C2 is already embedded - no C2 profile selection needed.

**Build pipeline:**

```
Operator → Mythic → Dolos container ──SSH──→ Remote server
                                      ──SFTP──→ Upload payload
                                      ──SSH────→ Run encoder command
                                      ──SFTP──→ Download result
                                      ──SFTP──→ Cleanup workdir
                              ← Result (EXE) + Session log (.session.json)
```

**What gets logged (session log):**
Every SSH connection event, SFTP operation (upload, download, mkdir, remove),
the exact encoder command run, line-by-line stdout/stderr, exit codes, file magic
detection, and cleanup - all with ISO 8601 timestamps and elapsed time.

### Key Features

- **Per-profile SSH config** - Each encoder profile has its own SSH server, credentials, and command
- **Bypass profiles** - Encoders like ShellcodePack can use bypass profiles that appear as a dropdown
- **Auto-install tools** - Idempotent install scripts run on the remote server before encoding
- **Native wrapper flow** - Select payload via Mythic's built-in selector (no file dropdown)
- **No C2 profile selection** - The wrapped payload already has its C2; Dolos just transforms it
- **Full session logging** - Every SSH/SFTP event captured as a JSON artifact with timestamps
- **Success/failure detection** - Per-encoder, configurable success/fail strings in profile JSON
- **Automatic workdir cleanup** - Random temp directory per build, deleted after completion
- **Build progress steps** - 9 steps reported in the UI with ✅/❌ status indicators
- **Config-file based** - No more editing `.env` for encoder commands or SSH credentials

## Authors

- [@3mrgnc3](https://github.com/3mrgnc3/Dolos)

## Table of Contents

{{% children %}}