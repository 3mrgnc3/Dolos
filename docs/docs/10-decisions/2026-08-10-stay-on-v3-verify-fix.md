# Decision: Stay on Mythic v3 for now, upgrade to v4 separately

**Date**: 2026-08-10
**Status**: Decided

## Context

Full Mythic stack was torn down to clean state (removed all containers, volumes, images). Mythic v3.4.36 is re-provisioned fresh. The Dolos bug fix (v1.1.0) needs verification before moving to v4.

## Decision

- Stay on Mythic v3.4.36 for the current verification cycle
- Verify the Dolos v1.1.0 resync fix on v3 first
- Create `v3-stable` branch from verified working state
- Create `v4-port` branch from `v3-stable` for v4 migration work
- v4 upgrade is a separate effort, not mixed into the bug fix cycle