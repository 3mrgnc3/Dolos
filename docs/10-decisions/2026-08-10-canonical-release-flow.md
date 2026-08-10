# Decision: Canonical Release Flow for Mythic Service Packages

**Date:** 2026-08-10  
**Status:** Accepted  

## Context

When developing Mythic service packages (payload types, C2 profiles, wrapper types) that are distributed via both **GitHub** (source code) and **Docker Hub** (pre-built images), bug fixes must follow a canonical release flow. If we skip steps — e.g., copying fixed files into a running container without rebuilding the Docker image — we verify the fix locally but ship a broken image to other users.

## Decision

**Always follow the full canonical release flow for bug fixes:**

1. **Fix the code** in the local repo
2. **Bump the version** in `agent_capabilities.json`
3. **Update `config.json`** `remote_images` tag to match the new version
4. **Build the Docker image** locally with the new tag (`docker build -t user/repo:vX.Y.Z`) — no `sudo`
5. **Push the Docker image** to Docker Hub (`docker push user/repo:vX.Y.Z`) — **never `sudo docker push`** — run as the user so cached Docker Hub credentials are used, not root's
6. **Commit and push** all changes (code + version bumps + config) to GitHub — **never `sudo git push`** — run as the user so cached Git credentials are used, not root's
7. **Uninstall** the old version from Mythic (`mythic-cli uninstall`)
8. **Reinstall from GitHub** the canonical way (`mythic-cli install github ...`)
9. **Verify the bug is gone** in the freshly installed instance

No shortcut (file copy, `docker cp`, rebuilding from InstalledServices) is sufficient for a release. Only the full flow guarantees that other users pulling the package get the fix.

## Consequences

- Every bug fix release involves a GitHub push *and* a Docker Hub push
- The version in `config.json` `remote_images` must always match the Docker Hub tag
- Local container patching is fine for development/debugging, but never counts as a release
- This flow should be documented in the Mythic development skill as a mandatory checklist