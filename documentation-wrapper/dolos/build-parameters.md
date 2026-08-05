+++
title = "Build Parameters"
weight = 20
+++

## Build Parameters

When you create a Dolos wrapper, you'll see these parameters organized by group.
The **wrapped payload is selected separately** via Mythic's native "Create Wrapper"
flow — it's not a build parameter.

<svg viewBox="0 0 600 320" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:600px;">
  <rect width="600" height="320" rx="12" fill="#1a1d23" stroke="#2a2f3a" stroke-width="1"/>
  <text x="300" y="30" font-family="system-ui" font-size="16" fill="#4a9eff" text-anchor="middle" font-weight="bold">Create Wrapper: Dolos</text>

  <!-- Wrapped payload selector -->
  <rect x="30" y="45" width="540" height="50" rx="6" fill="#1e2a3a" stroke="#f59e0b" stroke-width="2"/>
  <text x="50" y="68" font-family="system-ui" font-size="12" fill="#f59e0b" font-weight="bold">Wrapped Payload</text>
  <text x="50" y="85" font-family="system-ui" font-size="11" fill="#888">Select a previously built payload (Apollo, Merlin, etc.)</text>

  <!-- No C2 Profile section - explicitly absent -->
  <rect x="30" y="105" width="540" height="30" rx="6" fill="#2a1e1e" stroke="#666" stroke-width="1" stroke-dasharray="4"/>
  <text x="300" y="125" font-family="system-ui" font-size="11" fill="#666" text-anchor="middle">✕ No C2 Profile selection — C2 is in the wrapped payload</text>

  <!-- Build params -->
  <rect x="30" y="150" width="540" height="40" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="168" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Encoder</text>
  <text x="200" y="168" font-family="system-ui" font-size="12" fill="#e0e0e0">ChooseOne — PyEncoder_v1.0 ▾</text>
  <text x="50" y="183" font-family="system-ui" font-size="10" fill="#888">Remote command template from DOLOS_REMOTE_COMMAND</text>

  <rect x="30" y="200" width="540" height="30" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="220" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Timeout</text>
  <text x="200" y="220" font-family="system-ui" font-size="12" fill="#e0e0e0">Number — 300</text>

  <rect x="30" y="240" width="540" height="30" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="260" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Success String</text>
  <text x="200" y="260" font-family="system-ui" font-size="12" fill="#e0e0e0">String — ENCODING_SUCCESS</text>

  <rect x="30" y="280" width="540" height="30" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="300" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Fail String</text>
  <text x="200" y="300" font-family="system-ui" font-size="12" fill="#e0e0e0">String — ENCODING_FAILED</text>
</svg>

### Remote Command

#### Encoder (required)

Select an encoder command from the dropdown. The available options are loaded from
the `DOLOS_REMOTE_COMMAND` environment variable in `.env`. Each option represents
a command template that will be executed on the remote server.

<svg viewBox="0 0 600 200" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:600px;">
  <rect width="600" height="200" rx="8" fill="#1a1d23" stroke="#2a2f3a"/>
  <text x="300" y="25" font-family="system-ui" font-size="13" fill="#a855f7" text-anchor="middle" font-weight="bold">Encoder Dropdown → Command Resolution</text>
  <rect x="20" y="40" width="180" height="140" rx="6" fill="#252d3d" stroke="#a855f7"/>
  <text x="110" y="65" font-family="monospace" font-size="10" fill="#e0e0e0" text-anchor="middle">.env DOLOS_REMOTE_COMMAND</text>
  <text x="110" y="85" font-family="monospace" font-size="9" fill="#22c55e">"PyEncoder_v1.0":</text>
  <text x="110" y="98" font-family="monospace" font-size="8" fill="#888">  "py C:\tools\enc.py</text>
  <text x="110" y="110" font-family="monospace" font-size="8" fill="#888">   {workdir}\{input}</text>
  <text x="110" y="122" font-family="monospace" font-size="8" fill="#888">   {workdir}\{output}"</text>
  <text x="110" y="145" font-family="monospace" font-size="9" fill="#f59e0b">"Donut_x64":</text>
  <text x="110" y="158" font-family="monospace" font-size="8" fill="#888">  "C:\tools\donut.exe ..."</text>
  <line x1="210" y1="110" x2="260" y2="110" stroke="#a855f7" stroke-width="2" marker-end="url(#arrowhead)"/>
  <rect x="270" y="40" width="310" height="140" rx="6" fill="#252d3d" stroke="#22c55e"/>
  <text x="425" y="65" font-family="monospace" font-size="10" fill="#22c55e" text-anchor="middle">Resolved Command</text>
  <text x="285" y="90" font-family="monospace" font-size="9" fill="#e0e0e0">py C:\tools\encoder.py</text>
  <text x="285" y="105" font-family="monospace" font-size="9" fill="#e0e0e0">  C:\Windows\Temp\wd_a3f7kx\wd_in.bin</text>
  <text x="285" y="120" font-family="monospace" font-size="9" fill="#e0e0e0">  C:\Windows\Temp\wd_a3f7kx\wd_out.bin</text>
  <text x="285" y="150" font-family="system-ui" font-size="10" fill="#888">{workdir} → C:\Windows\Temp\wd_a3f7kx</text>
  <text x="285" y="165" font-family="system-ui" font-size="10" fill="#888">{input} → wd_in.bin</text>
  <text x="285" y="178" font-family="system-ui" font-size="10" fill="#888">{output} → wd_out.bin</text>
</svg>

See [Encoder Setup](encoder-setup) for instructions on adding new encoder commands.

#### Timeout (default: 300)

Timeout in seconds for the remote command. If the encoder takes longer than this,
the build will fail with a timeout error.

#### Success String (default: ENCODING_SUCCESS)

A string to search for in the command's stdout to confirm successful encoding. This
is critical for the pipeline to know when file transfer should begin. If the encoder
prints `ENCODING_SUCCESS` to stdout, the build detects this and proceeds.

#### Fail String (default: ENCODING_FAILED)

A string to search for in stdout/stderr to detect failure. If found, the build marks
the result as failed regardless of exit code.

### No SSH Input Fields

SSH configuration is read entirely from environment variables — there are no input
fields in the build dialog. The build steps automatically verify:

- ✅ SSH connectivity to `DOLOS_SSH_HOST`:`DOLOS_SSH_PORT`
- ✅ Password authentication with `DOLOS_SSH_USERNAME`/`DOLOS_SSH_PASSWORD`
- ✅ SFTP write test (upload + delete a small test file)

If connection fails, the build step shows ❌ with an error message pointing to the
relevant environment variable to fix.