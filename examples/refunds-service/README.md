# refunds-service (synthetic)

A synthetic payments service in a PCI cardholder-data environment, used to demonstrate Compliance
Support. None of the code is real, and none of the keys are real credentials.

The fixture demonstrates precision. It combines planted violations with clean code, so the plugin can be
seen to flag the correct lines and leave the rest untouched. An `audit_log.record()` helper is present,
which lets the agent reference the exact call a money-moving handler should make. One file sits outside
PCI scope and carries a dummy key, which the plugin correctly ignores.

> The hardcoded keys are generic dummy strings, not real `sk_live_...` values, so the public repository
> does not trigger secret scanners. The heuristic still detects them.

## Expected result per file

| File | In scope? | What is here | Result |
|---|---|---|---|
| `src/api/handlers/refund.py` | Yes | logs `user.email` and `card.number`; hardcoded `PROCESSOR_API_KEY`; `verify=False`; issues a refund with no `audit_log.record()` | the demo file; carries all four issues |
| `src/api/handlers/balance.py` | Yes | read-only; logs only an internal account id; parameterized query | clean, not flagged |
| `src/api/auth/middleware.py` | Yes | `require_scope` access-control decorator | clean, not flagged |
| `src/audit/audit_log.py` | Yes | the `record()` helper that money-moving handlers should call | clean (it is the helper) |
| `src/db/queries.py` | Yes | bound-parameter queries, no string-built SQL | clean, not flagged |
| `src/crypto/tokens.py` | Yes | `bcrypt` (approved) next to a legacy `md5` fingerprint | weak-crypto example for the hook |
| `src/config/settings.py` | Yes | secrets read from `os.environ` | clean, not flagged |
| `../../scripts/dev_seed.py` | No, out of scope | a dummy dev key under `scripts/` | correctly ignored, since the path is out of scope |

## The four checks in this fixture

| Check | Enforced by | Where it fires |
|---|---|---|
| PII or cardholder data in logs or errors | agent `compliance-review` | `refund.py` (`user.email`, `card.number`) |
| Money-moving action with no audit-log entry | agent `compliance-review` | `refund.py` (no `audit_log.record()`) |
| Hardcoded secret | hook `scan.sh` (blocks) | `refund.py` `PROCESSOR_API_KEY` |
| Weak crypto or TLS verify off | hook `scan.sh` (blocks) | `refund.py` `verify=False`; `tokens.py` `md5` |

The two hook checks block automatically as code is written. The two agent checks run on request, through
the `/compliance-support:compliance-review` command. See the repository root `README.md` for the full
demonstration.
