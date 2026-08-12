+++
title = "Build Parameters"
weight = 20
+++

## Build Parameters

When creating a Dolos wrapper in Mythic, you'll see these build parameters:

### Encoder (required, ChooseOne)

Select which encoder profile to use. Populated from the `NN_*.json` files in `/Mythic/`.
Only profiles with `enabled: true` appear in the dropdown.

Each encoder profile connects to a specific remote SSH server and runs a specific
encoding command. You can have multiple profiles for different servers, different tools,
or different bypass configurations.

### Bypass Profile (conditional, ChooseOne)

Shown only when the selected encoder has `bypass_refs` in its profile. Bypass profiles
are additional JSON files in `/Mythic/` that configure EDR evasion techniques. For example,
[Balliskit ShellcodePack](https://balliskit.com/) supports AMSI bypass and ETW patching
profiles that change the encoding behavior.

The selected bypass profile name is passed to the encoder command via the
`{bypass_profile}` placeholder. Only one bypass profile can be selected per build.

### Timeout (optional, ChooseOneCustom, default: 300)

How long to wait for the remote encoder command to complete, in seconds. You can type
a custom value. This overrides the profile's `timeout` field when set to a non-zero value.

Useful for complex encoders like ShellcodePack that may need more time for large payloads
or remote servers under load.

### Regenerate Shellcode (boolean, default: true)

If the inner payload already has a Dolos wrapper build, Dolos rebuilds it with a fresh
UUID instead of failing. This prevents duplicate wrapper errors when re-wrapping an
already-wrapped payload.