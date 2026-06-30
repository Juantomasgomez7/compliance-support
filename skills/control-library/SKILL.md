---
name: control-library
description: The data-protection control rules for a PCI-scoped codebase, covering what counts as a violation and the approved fix, mapped to PCI DSS, SOC 2, and GDPR. Knowledge for reviewing regulated code.
---

# Control library

The single source of truth for what counts as a data-protection violation and what the approved fix is.
The `compliance-review` agent preloads this to make its two judgment calls (CTRL-1, CTRL-2) and to cite
controls. The hook (`scan.sh`) enforces the two deterministic controls (CTRL-3, CTRL-4) by blocking the
write.

**How to use these rules**
- Cite control IDs at the family level (for example "PCI Req 3 & 10"), not a specific sub-requirement.
  That is enough to be actionable without being falsely precise.
- Agent findings are flag-for-review: name the control, show the fix, and let the engineer apply it.
  They are not auto-applied and not audit-grade.
- Scope is not defined here. Which paths are in PCI scope lives once in `.compliance.yml`, read by both
  the hook and the agent.

---

## CTRL-1: PII or cardholder data in logs or errors
- **Maps to:** PCI DSS Req 3 & 10 · GDPR Art 5 & 32
- **Enforced by:** agent (judgment)
- **Violation:** writing personal data (email, name, address, government id) or cardholder data (full
  PAN / card number, CVV, magnetic-stripe or track data) into a log, an error message, or an exception.
  This includes f-strings, `%`, or `.format()` that interpolate such a field into a logging or exception
  call.
- **Not a violation:** logging a non-sensitive identifier, such as an internal account id, a tokenized
  reference, or a refund id.
- **Fix:** log a non-sensitive identifier instead of the raw value. Mask or tokenize if a reference is
  genuinely needed.

```python
# before: leaks PII (email) and cardholder data (card number) to logs
log.info("issuing refund %s for %s on card %s", refund_id, user.email, card.number)
# after: internal identifiers only
log.info("issuing refund %s for account %s", refund_id, account_id)
```

## CTRL-2: Money-moving or state-changing action without an audit-log entry
- **Maps to:** SOC 2 CC7.2 · PCI DSS Req 10
- **Enforced by:** agent (judgment)
- **Violation:** a handler that moves money or changes state (issue or reverse a refund, adjust a
  balance, change an entitlement) returns without recording an audit entry through the service's audit
  helper, `audit_log.record(...)`.
- **Not a violation:** read-only actions (balance or GET). They do not require an audit entry.
- **Fix:** call `audit_log.record(...)` after the action succeeds, with non-sensitive metadata only
  (never card data or PII).

```python
# after: record the state change for the audit trail
result = process_refund(refund_id)
audit_log.record(actor=user.id, action="refund.issued", resource=f"refund:{refund_id}")
return result
```

## CTRL-3: Hardcoded secrets or credentials
- **Maps to:** PCI DSS Req 8
- **Enforced by:** hook (deterministic, blocks the write)
- **Violation:** a literal secret in source: an API key, token, or password assigned to a variable or
  passed inline. This includes provider-format keys (`sk_live_…`, `AKIA…`, `ghp_…`, `xox…`) and
  high-entropy string literals assigned to a `*_KEY`, `*_SECRET`, `*_TOKEN`, or `*_PASSWORD` name.
- **Not a violation:** reading the secret from the environment or a secrets manager
  (`os.environ["PROCESSOR_API_KEY"]`).
- **Fix:** read the value at runtime from the environment or a secrets manager, and keep the literal out
  of source control entirely.

```python
# before: hardcoded credential in source (blocked)
PROCESSOR_API_KEY = "9c1f8e2a7b4d6051c3e9f0a2b8d4e6f1"
# after: injected from the environment
PROCESSOR_API_KEY = os.environ["PROCESSOR_API_KEY"]
```

## CTRL-4: Weak cryptography or disabled transport security
- **Maps to:** PCI DSS Req 3 & 4 · SOC 2 CC6.7
- **Enforced by:** hook (deterministic, blocks the write)
- **Violation:** using a weak or broken algorithm to protect data (MD5 or SHA-1 for security, DES, RC4,
  or AES in ECB mode), or disabling TLS verification on an outbound call (`verify=False`,
  `ssl._create_unverified_context()`).
- **Not a violation:** strong primitives (bcrypt, scrypt, or argon2 for secrets, AES-GCM for encryption)
  with TLS verification left on.
- **Fix:** use a strong primitive, and keep TLS verification enabled (`verify=True`, or the default).

```python
# before: TLS verification disabled (blocked)
requests.post(url, json=payload, verify=False)
# after: verification on (default)
requests.post(url, json=payload)
```
