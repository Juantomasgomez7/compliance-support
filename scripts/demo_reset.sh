#!/usr/bin/env bash
# Reset the example service to a clean starting state so you can run the demo again.
# Safe to run as many times as you like. Out of PCI scope, so the hook ignores it.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# 1. Remove anything a run may have generated or created.
rm -f compliance-report.md compliance-report.html
rm -f examples/refunds-service/src/api/handlers/payout.py

# 2. Restore demo source files a run may have edited. Needs a committed repo;
#    if nothing is committed yet, there is nothing to restore and that is fine.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git checkout -- examples/refunds-service scripts/dev_seed.py 2>/dev/null; then
    echo "Restored demo files from git."
  fi
fi

echo "Demo reset complete. Ready for the next run."
