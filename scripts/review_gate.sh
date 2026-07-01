#!/usr/bin/env bash
# Compliance Support, Stop-hook passive review gate.
#
# Thin, portable wrapper (twin of scan.sh). The real logic lives in
# review_gate.py so a single readable file parses the Stop payload, reads the
# .compliance.yml scope, asks git what changed, and decides whether to nudge —
# testable anywhere Python runs, with no extra binary to install. Keeping the
# hook entry a .sh keeps it firing identically on macOS and Windows (git-bash).
#
# stdin (the Stop payload) is inherited by Python via exec. The gate nudges by
# printing a `block` decision and exiting 0; otherwise it stays silent. It never
# blocks the stop when Python is unavailable (fail open).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pick a Python that actually RUNS, not one that merely exists (the Windows
# WindowsApps `python3` is a Store stub that no-ops).
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1 && [ "$("$cand" -c 'print(1)' 2>/dev/null)" = "1" ]; then
    exec "$cand" "$here/review_gate.py"
  fi
done

# No working Python on PATH: fail open, never block a stop.
exit 0
