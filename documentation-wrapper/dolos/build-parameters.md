+++
title = "Build Parameters"
weight = 20
+++

## Build Parameters

When creating a Dolos wrapper in Mythic, you'll see these build parameters:

### Encoder (required)

Select which encoder profile to use. Populated from the `00_*.json` files
in `/Mythic/`. Only enabled profiles appear.

### Bypass Profile (conditional)

Shown only when the selected encoder has bypass profiles configured. Bypass
profiles are additional JSON files referenced by `bypass_refs` in the encoder
profile.

### Timeout (optional, default: 300s)

How long to wait for the remote encoder command to complete. You can type a
custom value.

### Regenerate Shellcode (boolean, default: true)

If the inner payload already has a Dolos wrapper, Dolos rebuilds it with a
fresh UUID instead of failing.