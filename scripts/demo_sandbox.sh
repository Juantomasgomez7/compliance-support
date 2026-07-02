#!/usr/bin/env bash
# Build a standalone copy of the example refunds service in a SIBLING folder,
# so you can experience the plugin the way an engineer would: a plain service
# repo with its own .compliance.yml, and the plugin loaded from elsewhere,
# as a marketplace install would be. Safe to re-run; re-running resets it.
set -euo pipefail
plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sandbox="${1:-$plugin_root/../refunds-service-sandbox}"

rm -rf "$sandbox"
mkdir -p "$sandbox/scripts"
cp -R "$plugin_root/examples/refunds-service/src" "$sandbox/src"
cp "$plugin_root/scripts/dev_seed.py" "$sandbox/scripts/dev_seed.py"
find "$sandbox" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

cat > "$sandbox/.compliance.yml" <<'YML'
# The AppSec-owned scope + severity map for the refunds service.
scope:
  include:
    - "src/**"
  exclude:
    - "**/scripts/**"

checks:
  hardcoded_secret:   { severity: block }    # hook   - deterministic (CTRL-1)
  weak_crypto_or_tls: { severity: block }    # hook   - deterministic (CTRL-2)
  pii_in_logs:        { severity: review }   # agent  - judgment      (CTRL-3)
  missing_audit_log:  { severity: review }   # agent  - judgment      (CTRL-4)
YML

cat > "$sandbox/README.md" <<'MD'
# refunds-service

Issues and reverses card refunds against the payment processor. Code under
`src/` handles cardholder data; `.compliance.yml` defines the PCI scope.
MD

# Its own git history, so the turn-end gate can see what changed.
git -C "$sandbox" init -q -b main
git -C "$sandbox" config core.autocrlf false
git -C "$sandbox" add -A
git -C "$sandbox" -c user.name="demo-sandbox" -c user.email="demo@sandbox.local" commit -qm "refunds-service" >/dev/null

# Print paths in a form every shell on this OS accepts (cygpath on Windows).
sandbox_abs="$(cd "$sandbox" && pwd)"
if command -v cygpath >/dev/null 2>&1; then
  sandbox_disp="$(cygpath -m "$sandbox_abs")"
  plugin_disp="$(cygpath -m "$plugin_root")"
else
  sandbox_disp="$sandbox_abs"
  plugin_disp="$plugin_root"
fi

echo "Sandbox ready at: $sandbox_disp"
echo "Next:"
echo "  cd \"$sandbox_disp\""
echo "  claude --plugin-dir \"$plugin_disp\""
echo "Run the demo steps with paths relative to this repo (src/... instead of"
echo "examples/refunds-service/src/...). Re-run this script to reset."
