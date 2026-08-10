# Decision: Branching strategy for v3 and v4 compatibility

**Date**: 2026-08-10
**Status**: Planned (not yet executed)

## Decision

Maintain two long-lived branches:

1. **`v3-stable`** — Current working code, compatible with Mythic v3.x (uses `mythic_container` Python SDK). Branched from current `master` once v1.1.0 fix is verified.

2. **`v4-port`** — Port of Dolos to Mythic v4 (uses `MythicContainer` Go SDK or `MythicContainerPyPi` Python SDK). Branched from `v3-stable`, then modified for v4 API compatibility.

This lets users pick which version they need based on their Mythic deployment version.

## Rationale

- Mythic v3 and v4 have incompatible container SDKs
- v4 is still beta — some users need v3
- A single branch can't serve both
- Separate branches allow independent bug fixes and releases

## Not yet done

- Create `v3-stable` branch
- Create `v4-port` branch
- Port Dolos to v4 SDK