+++
title = "Build Parameters"
weight = 20
+++

## Build Parameters

When you create a Dolos wrapper, you'll see these parameters organized by group.
The **wrapped payload is selected separately** via Mythic's native "Create Wrapper"
flow — it's not a build parameter.

<svg viewBox="0 0 600 380" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:600px;">
  <rect width="600" height="380" rx="12" fill="#1a1d23" stroke="#2a2f3a" stroke-width="1"/>
  <text x="300" y="30" font-family="system-ui" font-size="16" fill="#4a9eff" text-anchor="middle" font-weight="bold">Create Wrapper: Dolos</text>

  <!-- Wrapped payload selector -->
  <rect x="30" y="45" width="540" height="50" rx="6" fill="#1e2a3a" stroke="#f59e0b" stroke-width="2"/>
  <text x="50" y="68" font-family="system-ui" font-size="12" fill="#f59e0b" font-weight="bold">Wrapped Payload</text>
  <text x="50" y="85" font-family="system-ui" font-size="11" fill="#888">Select a previously built payload (Apollo, Merlin, etc.)</text>

  <!-- No C2 Profile section -->
  <rect x="30" y="105" width="540" height="30" rx="6" fill="#2a1e1e" stroke="#666" stroke-width="1" stroke-dasharray="4"/>
  <text x="300" y="125" font-family="system-ui" font-size="11" fill="#666" text-anchor="middle">✕ No C2 Profile selection — C2 is in the wrapped payload</text>

  <!-- Build params -->
  <rect x="30" y="150" width="540" height="40" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="168" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Encoder</text>
  <text x="200" y="168" font-family="system-ui" font-size="12" fill="#e0e0e0">ChooseOne — PyEncoder_v1 ▾</text>
  <text x="50" y="183" font-family="system-ui" font-size="10" fill="#888">From configs/encoders/ encoder_profile.json</text>

  <rect x="30" y="200" width="540" height="35" rx="6" fill="#252d3d" stroke="#a855f7" stroke-width="1"/>
  <text x="50" y="218" font-family="system-ui" font-size="12" fill="#a855f7" font-weight="bold">Bypass Profile</text>
  <text x="200" y="218" font-family="system-ui" font-size="12" fill="#e0e0e0">ChooseOne — (None) ▾</text>
  <text x="50" y="228" font-family="system-ui" font-size="9" fill="#888">Only shown for encoders with bypass profiles</text>

  <rect x="30" y="245" width="540" height="30" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="265" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Timeout</text>
  <text x="200" y="265" font-family="system-ui" font-size="12" fill="#e0e0e0">Number — 0 (use profile default)</text>

  <rect x="30" y="285" width="540" height="30" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="305" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Success String</text>
  <text x="200" y="305" font-family="system-ui" font-size="12" fill="#e0e0e0">String — ENCODING_SUCCESS</text>

  <rect x="30" y="325" width="540" height="30" rx="6" fill="#252d3d" stroke="#4a9eff" stroke-width="1"/>
  <text x="50" y="345" font-family="system-ui" font-size="12" fill="#4a9eff" font-weight="bold">Fail String</text>
  <text x="200" y="345" font-family="system-ui" font-size="12" fill="#e0e0e0">String — ENCODING_FAILED</text>
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

#### Timeout (default: from profile)

Timeout in seconds for the remote command. If set to 0 (default), uses the
encoder profile's `timeout` field. Override for slow servers or complex encoders.

#### Success String (default: ENCODING_SUCCESS)

A string to search for in the command's stdout to confirm successful encoding.

#### Fail String (default: ENCODING_FAILED)

A string to search for in stdout/stderr to detect failure. If found, the build
is marked as failed regardless of exit code.

### No SSH Input Fields

SSH configuration is read from encoder profiles — there are no SSH input fields
in the build dialog. Each encoder profile specifies its own server, credentials,
and command. The build steps automatically verify:

- ✅ SSH connectivity to the profile's `ssh_server.host`:`port`
- ✅ Key or password authentication
- ✅ SFTP write test (upload + delete a small test file)