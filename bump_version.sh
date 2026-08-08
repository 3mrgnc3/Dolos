#!/usr/bin/env bash
# bump_version.sh - Update the version in all files from a single source.
#
# Usage: ./bump_version.sh <version>
# Example: ./bump_version.sh 1.0.5
#
# The canonical version is stored in:
#   Payload_Type/dolos/dolos/agent_capabilities.json  →  "agent_version": "X.Y.Z"
#
# All other version references are derived from that file:
#   - config.json                          →  remote_images tag
#   - agent_capabilities.json (root)        →  copied from internal
#   - documentation-wrapper/dolos/_index.md  →  displayed version
#   - README.md                             →  changelog entry (manual)

set -euo pipefail

VERSION="${1:?Usage: $0 <version>}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
INTERNAL_CAPABILITIES="$ROOT/Payload_Type/dolos/dolos/agent_capabilities.json"

echo "→ Setting version to $VERSION"

# 1. Update canonical source: internal agent_capabilities.json
python3 -c "
import json
with open('$INTERNAL_CAPABILITIES') as f:
    data = json.load(f)
data['agent_version'] = '$VERSION'
with open('$INTERNAL_CAPABILITIES', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"
echo "  ✓ Payload_Type/dolos/dolos/agent_capabilities.json"

# 2. Copy to root agent_capabilities.json
cp "$INTERNAL_CAPABILITIES" "$ROOT/agent_capabilities.json"
echo "  ✓ agent_capabilities.json (root)"

# 3. Update config.json remote_images tag
python3 -c "
import json
with open('$ROOT/config.json') as f:
    data = json.load(f)
data['remote_images']['dolos'] = '3mrgnc3/mythic-c2-dolos:v$VERSION'
with open('$ROOT/config.json', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"
echo "  ✓ config.json"

# 4. Update documentation _index.md
sed -i "s/\*\*Current version: v[0-9.]*\*\*/\*\*Current version: v$VERSION\*\*/" \
    "$ROOT/documentation-wrapper/dolos/_index.md"
echo "  ✓ documentation-wrapper/dolos/_index.md"

echo ""
echo "Done. All version references updated to $VERSION"
echo ""
echo "Remaining manual steps:"
echo "  1. Add changelog entry to README.md"
echo "  2. Build Docker image:  docker build --no-cache -t 3mrgnc3/mythic-c2-dolos:v$VERSION Payload_Type/dolos/"
echo "  3. Push Docker image:   docker push 3mrgnc3/mythic-c2-dolos:v$VERSION"
echo "  4. Git commit & tag:     git add -A && git commit -m 'release: v$VERSION' && git tag v$VERSION"
echo "  5. Git push:             git push origin master --tags"