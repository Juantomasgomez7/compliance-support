---
description: Review changed PCI-scoped code for data-protection issues (PII in logs, missing audit log). Add --report to also generate a shareable compliance document.
---
Run a data-protection review of in-scope code using the **compliance-review** agent, then present the
findings clearly. This is a *flag-for-review* helper: it explains issues and proposes fixes. It never
edits code, and it never claims audit-grade certainty.

## 1. Choose the files to review

- If `$ARGUMENTS` names file paths (ignore flags like `--report`), review exactly those.
- Otherwise review the **in-scope files changed in the working tree**: run `git status --porcelain`,
  and keep paths that match `scope.include` (and not `scope.exclude`) in `.compliance.yml`.
- If there are no changed in-scope files, review all files under `scope.include`.

## 2. Review

For each target file, dispatch the `compliance-review` agent and collect its findings (CTRL-1 PII in
logs, CTRL-2 missing `audit_log.record()`). Out-of-scope files are skipped by design.

## 3. Show the result inline

Group by file: for each finding give the control and line, one sentence on what is wrong, and the
concrete fix. Also name the files that were reviewed and came back clean. This shows the gate is precise,
not noisy.

## 4. Report, only if `$ARGUMENTS` contains `--report`

If, and only if, `--report` was passed, generate the report from the agent's findings. Collect the JSON
findings block from each reviewed file into one JSON array, including in-scope files that came back clean,
and pass it to the renderer on stdin:

```bash
python scripts/render_report.py <<'FINDINGS'
[ ...the array of per-file JSON results: {"file", "in_scope", "findings": [...]}... ]
FINDINGS
```

The renderer writes `compliance-report.md` and a styled, browser-ready `compliance-report.html` at the
repo root. It supplies the control names and the "why it matters" text, so do not hand-write the report.
The renderer also runs a deterministic CTRL-3/CTRL-4 confirmation over the reviewed files (the same
patterns the hook enforces), so both reports present all four controls; the agent itself still reports
only CTRL-1/CTRL-2. Tell the user both files were written and that the HTML opens in a browser.

If `--report` was not passed, write no file, and end with:

> Tip: run `/compliance-support:compliance-review --report` for a shareable report (Markdown and HTML).
