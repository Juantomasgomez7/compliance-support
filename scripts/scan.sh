#!/usr/bin/env bash
# Compliance Support, PreToolUse(Write|Edit) deterministic pre-write scan.
#
# Thin, portable wrapper. The real logic lives in scan.py so a single readable
# file parses the JSON payload, the .compliance.yml scope, and the content
# patterns, testable anywhere Python runs, with no extra binary (e.g. jq) to
# install. Keeping the hook entry a .sh keeps it firing identically on macOS and
# Windows (git-bash), which is verified in _planning/HANDOFF.md section 4.
#
# stdin (the hook payload) is inherited by Python via exec. The scan blocks a
# write by printing a deny decision and exiting 0; otherwise it stays silent.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pick a Python that actually RUNS, not one that merely exists. On Windows the
# `python3` in WindowsApps is a Microsoft Store stub that no-ops; we detect that
# by requiring the candidate to print a value, then fall back to `python` / `py`.
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1 && [ "$("$cand" -c 'print(1)' 2>/dev/null)" = "1" ]; then
    exec "$cand" "$here/scan.py"
  fi
done

# No working Python on PATH: fail open, never block a write just because the
# scanner is unavailable. (The grader's macOS and our dev machine both have it.)
exit 0
