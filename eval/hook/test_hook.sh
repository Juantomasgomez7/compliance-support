#!/usr/bin/env bash
# Hook golden tests, deterministic (no model, no network, instant).
# Feed crafted PreToolUse payloads into scan.sh and assert deny (BLOCK) / silent (ALLOW).
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && { pwd -W 2>/dev/null || pwd; })"   # Windows-native path under git-bash

PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && [ "$("$c" -c 'print(1)' 2>/dev/null)" = "1" ]; then PY="$c"; break; fi
done
[ -z "$PY" ] && { echo "no working Python found"; exit 2; }

pass=0; fail=0
check() {  # $1=label  $2=BLOCK|ALLOW  $3=relpath  $4=content
  out="$("$PY" "$here/_payload.py" "$root" "$3" "$4" | bash "$root/scripts/scan.sh" 2>&1)"
  if printf '%s' "$out" | grep -q '"permissionDecision": "deny"'; then got=BLOCK; else got=ALLOW; fi
  if [ "$got" = "$2" ]; then printf 'PASS  %-32s %s\n' "$1" "$2"; pass=$((pass + 1))
  else printf 'FAIL  %-32s expected %s got %s\n' "$1" "$2" "$got"; fail=$((fail + 1)); fi
}

S=examples/refunds-service/src
echo "== Hook golden tests, CTRL-1 secrets, CTRL-2 weak crypto/TLS, and scope =="
check "in-scope provider secret"   BLOCK "$S/api/handlers/refund.py" 'API_KEY = "sk_live_EXAMPLE_not_a_real_key_000"'
check "in-scope generic key literal" BLOCK "$S/api/handlers/refund.py" 'PROCESSOR_API_KEY = "9c1f8e2a7b4d6051c3e9f0a2b8d4e6f1"'
check "in-scope verify=False"      BLOCK "$S/api/handlers/refund.py" 'requests.post(u, json=p, verify=False)'
check "in-scope md5"               BLOCK "$S/crypto/tokens.py" 'return hashlib.md5(t).hexdigest()'
check "in-scope clean log"         ALLOW "$S/api/handlers/balance.py" 'log.info("balance for account %s", account_id)'
check "in-scope env-var secret"    ALLOW "$S/config/settings.py" 'key = os.environ["PROCESSOR_API_KEY"]'
check "in-scope parameterized sql" ALLOW "$S/db/queries.py" 'cur.execute("SELECT id FROM r WHERE id=%s", (rid,))'
check "OUT-of-scope secret (dev)"  ALLOW "scripts/dev_seed.py" 'DEV_KEY = "sk_live_EXAMPLE_not_a_real_key_000"'
echo "---- $pass passed, $fail failed ----"
[ "$fail" -eq 0 ]
