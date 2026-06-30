# Compliance Support

Compliance Support is a Claude Code plugin for back-end developers working on PCI cardholder-data services within Capital One bank.

The plugin's objective is to catch, flag and suggest corrections for data-protection mistakes before code reaches code review or audit stages.

Concretely, the plugin helps engineers ensure they ship compliant code through a two-stage approach:

1. Gate 1: Pre-write hook that blocks hardcoded secrets and weak cryptography.
2. Gate 2: Upon request, an agent reviews code for personal data in logs and for money-moving actions that have no audit-log entry.

## Requirements

Claude Code and Python 3.

## Installation

```bash
git clone https://github.com/Juantomasgomez7/compliance-support.git
cd compliance-support
claude --plugin-dir .
```

The plugin loads for that session.

## Checks

| Check                                               | When              | Control                         |
| --------------------------------------------------- | ----------------- | ------------------------------- |
| Hardcoded secret or credential                      | blocks on write   | PCI Req 8                       |
| Weak crypto (MD5, DES, ECB) or TLS verification off | blocks on write   | PCI Req 3 & 4, SOC 2 CC6.7      |
| Personal or cardholder data in logs or errors       | review on request | PCI Req 3 & 10, GDPR Art 5 & 32 |
| Money-moving action with no audit-log entry         | review on request | SOC 2 CC7.2, PCI Req 10         |

Reviews flag issues for an engineer to fix. They are not an audit sign-off.

Control definitions, with the violation and the fix for each, live in `skills/control-library/SKILL.md`.
The blocking checks stop known-bad patterns at the keyboard, before they reach a commit. The review checks
add the judgment a pattern scanner cannot: personal data in logs, and money-moving actions with no audit
trail.

## Scope and coverage

`.compliance.yml` lists the in-scope paths. To cover a new service, add its path. The blocker and the
review both read this file.

Because the blocker is a Claude Code `PreToolUse` hook, and a hook observes only its host's actions, coverage is bounded to code written through Claude Code. Code introduced another way produces no hook event, so those paths rely on whatever else already guards them and will not trigger the blocker. As such, it is recommended to use Claude Code when working on regulated repositories to maximize value extraction from this plugin.

## Validation Test (Optional)

Optional. The repository includes a synthetic service in `examples/refunds-service/` so you can confirm the plugin is active and see what a block and a review look like, without touching real code. Run the steps below inside the session.

**1. Block a secret on write.** Instruct Claude Code:

> Add a handler examples/refunds-service/src/api/handlers/payout.py that calls the processor with
> PROCESSOR_API_KEY = "sk_live_EXAMPLE_not_a_real_key_000" and verify=False.

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

## Ownership

The checks encode regulatory controls, so ownership is shared. The plugin is run by the engineering team
in the PCI cardholder-data environment (the backend and payments services that fall under PCI DSS, SOC 2,
and GDPR); while the security and compliance function owns the substance: the control definitions in
`skills/control-library/SKILL.md` and the in-scope paths in `.compliance.yml`. Keeping those two files
current as controls or scope change is a compliance responsibility, not only an engineering one.

## License

MIT.
