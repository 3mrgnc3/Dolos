+++
title = "Build Parameters"
weight = 20
+++

## Build Parameters

When you create a Dolos wrapper, you'll see these parameters organized by group.
The **wrapped payload is selected separately** via Mythic's native "Create Wrapper"
flow - it's not a build parameter.

<svg viewBox="0 0 600 310" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:600px;">
  <rect width="600" height="310" rx="12" fill="#1a1d23" stroke="#2a2f3a" stroke-width="1"/>
  <text x="300" y="30" font-family="system-ui" font-size="16" fill="#4a9eff" text-anchor="middle" font-weight="bold">Create Wrapper: Dolos</text>

  <!-- Wrapped payload selector -->
  <rect x="30" y="45" width="540" height="50" rx="6" fill="#1e2a3a" stroke="#f59e0b" stroke-width="2"/>
  <text x="50" y="68" font-family="system-ui" font-size="12" fill="#f59e0b" font-weight="bold">Wrapped Payload</text>
  <text x="50" y="85" font-family="system-ui" font-size="11" fill="#888">Select a previously built payload (Apollo, Merlin, etc.)</text>

  <!-- No C2 Profile section -->
  <rect x="30" y="105" width="540" height="30" rx="6" fill="#2a1e1e" stroke="#666" stroke-width="1" stroke-dasharray="4"/>
  <text x="300" y="125" font-family="system-ui" font-size="11" fill="#666" text-anchor="middle">✕ No C2 Profile selection - C2 is in the wrapped payload</text>

  <!-- Build params -->
  <rect x="30" y="150" width="540" height="40" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="168" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Encoder</text>
  <text x="200" y="168" font-family="system-ui" font-size="12" fill="#e0e0e0">ChooseOne - PyEncoder_v1 ▾</text>
  <text x="50" y="183" font-family="system-ui" font-size="10" fill="#888">From configs/encoders/ encoder_profile.json</text>

  <rect x="30" y="200" width="540" height="40" rx="6" fill="#252d3d" stroke="#a855f7" stroke-width="1"/>
  <text x="50" y="218" font-family="system-ui" font-size="12" fill="#a855f7" font-weight="bold">Bypass Profile</text>
  <text x="200" y="218" font-family="system-ui" font-size="12" fill="#e0e0e0">ChooseOne - (None) ▾</text>
  <text x="50" y="233" font-family="system-ui" font-size="10" fill="#888">Only shown for encoders with bypass profiles</text>

  <rect x="30" y="250" width="540" height="40" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="268" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Timeout</text>
  <text x="200" y="268" font-family="system-ui" font-size="12" fill="#e0e0e0">ChooseOneCustom - 300 ▾ (or type custom)</text>
  <text x="50" y="283" font-family="system-ui" font-size="10" fill="#888">Default from profile; type custom value to override</text>

  <rect x="30" y="300" width="540" height="35" rx="6" fill="#1e3a2a" stroke="#22c55e" stroke-width="1"/>
  <text x="50" y="323" font-family="system-ui" font-size="12" fill="#22c55e" font-weight="bold">Regenerate Shellcode</text>
  <text x="260" y="323" font-family="system-ui" font-size="12" fill="#e0e0e0">Boolean - true ☑</text>
  <text x="380" y="323" font-family="system-ui" font-size="10" fill="#888">(auto-rebuild on dedup)</text>
</svg>

### Remote Command

#### Encoder (required)

Select an encoder profile from the dropdown. The available options are loaded from
`configs/encoders/*/encoder_profile.json` files. Each profile specifies its own
SSH server, command template, and optional bypass profiles.

If no profiles are configured, the dropdown shows "(no profiles configured)" and
builds will fail until profiles are added.

#### Bypass Profile (conditional)

Only shown when the selected encoder has bypass profiles configured. The dropdown
lists profiles in the format **"ProjectName / ProfileName Bypass"** (e.g.,
"Balliskit / Cortex Bypass"). Select **(None)** to skip bypass.

The `{bypass_profile}` placeholder in the command template resolves to the
selected profile's stem filename (e.g., `cortex_bypass_profile`).

#### Timeout (ChooseOneCustom)

Timeout in seconds for the remote encoder command. The dropdown shows the selected
encoder's default timeout plus common alternatives (60, 120, 300, 600, 900, 1800).
You can also type any custom value.

To change the default timeout permanently, edit `timeout` in the encoder profile JSON.

#### Regenerate Shellcode (default: true)

When enabled (default), if the selected payload has already been wrapped by Dolos,
the inner payload is automatically rebuilt with the same configuration but a new UUID.
This avoids duplicate-callback confusion. Disable to proceed with the same shellcode.

### Per-Encoder Settings (not in the UI)

These settings come from `encoder_profile.json` - they're not editable in the build dialog
because they're constants tied to each encoder:

| Setting | Default | Description |
|---------|---------|-------------|
| `success_string` | `ENCODING_SUCCESS` | String in stdout confirming success |
| `fail_string` | `ENCODING_FAILED` | String in stdout/stderr indicating failure |
| `install_tools` | `false` | Whether to auto-install tools before encoding |
| `toolset` | `""` | Subdirectory under `configs/tools/` for install scripts |

### No SSH Input Fields

SSH configuration is read from encoder profiles - there are no SSH input fields
in the build dialog. Each encoder profile specifies its own server, credentials,
and command. The build steps automatically verify:

- ✅ SSH connectivity to the profile's `ssh_server.host`:`port`
- ✅ Key or password authentication
- ✅ SFTP write test (upload + delete a small test file)