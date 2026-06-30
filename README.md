# Compliance Support

Compliance Support is a Claude Code plugin for engineers working on PCI cardholder-data services. It
catches data-protection mistakes as code is written, before they reach code review or an audit.

It blocks hardcoded secrets and weak cryptography on write. On request, it reviews code for personal data
in logs and for money-moving actions that have no audit-log entry. It runs only on the paths marked in
scope, and only on code written through Claude Code.

## Requirements

Claude Code and Python 3.

## Installation

```bash
git clone <repo-url> compliance-support
cd compliance-support
claude --plugin-dir .
```

The plugin loads for that session.

## Quick start

The repository includes a synthetic service in `examples/refunds-service/` to demonstrate the plugin
without real code. Run the steps below inside the session.

**1. Block a secret on write.** Instruct Claude Code:

> Add a handler examples/refunds-service/src/api/handlers/payout.py that calls the processor with
> PROCESSOR_API_KEY = "sk_live_EXAMPLE_not_a_real_key_000" and verify=False.

The write is blocked before it lands. The message names the control and tells the engineer to read the
key from the environment.

**2. Run a review on request.** Type `/compliance` and select the command, or enter it in full:

```
/compliance-support:compliance-review examples/refunds-service/src/api/handlers/refund.py
```

The review flags the card number in the log and the refund with no audit entry, cites the control, and
shows the fix. It does not edit code. Append `--report` to also write a shareable report, as Markdown
and as a styled `compliance-report.html` that opens in a browser.

**3. Confirm scope.** Add the same key to `scripts/dev_seed.py`. The write proceeds, because that path is
not in PCI scope.

To reset the example, run `bash scripts/demo_reset.sh`.

## Checks

| Check | When | Control |
|---|---|---|
| Hardcoded secret or credential | blocks on write | PCI Req 8 |
| Weak crypto (MD5, DES, ECB) or TLS verification off | blocks on write | PCI Req 3 & 4, SOC 2 CC6.7 |
| Personal or cardholder data in logs or errors | review on request | PCI Req 3 & 10, GDPR Art 5 & 32 |
| Money-moving action with no audit-log entry | review on request | SOC 2 CC7.2, PCI Req 10 |

Reviews flag issues for an engineer to fix. They are not an audit sign-off.

Control definitions, with the violation and the fix for each, live in `skills/control-library/SKILL.md`.
The blocking checks stop known-bad patterns at the keyboard, before they reach a commit. The review checks
add the judgment a pattern scanner cannot: personal data in logs, and money-moving actions with no audit
trail.

## Scope

`.compliance.yml` lists the in-scope paths. To cover a new service, add its path. The blocker and the
review both read this file.

## License

MIT.
