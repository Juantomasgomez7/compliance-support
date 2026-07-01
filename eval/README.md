# Evaluation

Compliance Support makes two kinds of check, and each is tested accordingly. Deterministic checks are
verified with exact golden tests. The agent's judgment is measured with precision and recall.

## Hook: deterministic golden tests

This suite feeds crafted `PreToolUse` payloads into `scan.sh` and asserts block or allow for CTRL-3
(secrets), CTRL-4 (weak crypto and TLS-off), and scope. It uses no model and no network, and runs in a
second.

```bash
bash eval/hook/test_hook.sh
```

## Agent: precision and recall

This script runs the `compliance-review` agent against the labeled cases in `cases.yml` and scores the
control IDs it flags (CTRL-1 PII in logs, CTRL-2 missing audit) against the expected set.

```bash
python eval/run_eval.py
```

It spawns a few `claude -p` runs and takes a couple of minutes. It uses the existing Claude login and
needs no new credentials. The agent is a language model, so the numbers are measured per run rather than
guaranteed, and the harness prints what it observed.

## Stop-hook gate: unit tests

The Tier-2 `Stop` hook (`scripts/review_gate.py`) is deterministic too: it decides whether to nudge a
review of the PCI-scoped files a turn changed. Its scope filtering, the `stop_hook_active` loop guard,
and the once-per-change-set sentinel are covered by `tests/test_review_gate.py`.

```bash
python -m unittest discover -s tests
```

`cases.yml` holds the labeled ground truth, known by construction because the fixture is planted. Evals
for the probabilistic agent, golden tests for the deterministic hook: the right tool for each kind of
check.

This directory is not part of the install path. It is evidence to run on demand, not a dependency of the
plugin.
