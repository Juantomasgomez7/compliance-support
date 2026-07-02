# The compliance report

`/compliance-support:compliance-review --report` writes two files at the repo root:

- `compliance-report.md` — the same report in plain text (good for diffs, CI logs, terminals).
- `compliance-report.html` — a branded, self-contained report. The command opens it in your default browser on its own, and it attaches cleanly to an email.

Both carry the same content; the HTML adds the logo, colors, and layout.

Both come from **`scripts/render_report.py`**, built from the findings the `compliance-review`
agent emits. The report is a *flag-for-review* artifact, not an audit sign-off.

## What a report covers

A report describes **one manual run** — the in-scope files reviewed at the moment you ran the
command (named files, else changed in-scope files, else all in-scope files). It is not a session
or a time window; the HTML report states this scope at the top.

It presents all four controls:

| Control | Checked by | In the report |
|--|--|--|
| CTRL-1 Hardcoded secret | pre-write hook, re-confirmed here | coverage row (finding if one is found) |
| CTRL-2 Weak crypto / TLS off | pre-write hook, re-confirmed here | coverage row (finding if one is found) |
| CTRL-3 Personal/card data in logs | AI agent (judgment) | finding + coverage row |
| CTRL-4 Money-moving action w/o audit log | AI agent (judgment) | finding + coverage row |

CTRL-1/CTRL-2 are enforced live by the hook (`scripts/scan.py`), which blocks bad writes before
they land. The report re-scans the reviewed files for them using the **same patterns**, so it shows
all four controls and catches anything introduced outside Claude Code. Both the Markdown and HTML
reports carry these confirmatory findings.

## How to customize it

Everything lives in **`scripts/render_report.py`**:

- **Control names, the per-control standards mapping, "why it matters" text, and fixes** — the
  `CONTROLS` dict (the `maps_to` field is what shows in the coverage table's Standards column and on
  each finding card).
- **The "What we check against" reference** (plain-English meaning of each standard clause) — the
  `STANDARDS` list.
- **Plain-English coverage-table text** — `GUARD_AGAINST`, `HOW_CHECKED`, `KIND_LABEL`.
- **The glossary** ("How to read this report") — the `<dl class=gloss>` block in `render_html`.
- **Brand colors and logo** — `BRAND_NAVY`, `BRAND_RED`, `ORG_NAME`, `LOGO_PATH` (image at
  `assets/capital-one-logo.png`). The colors are also defined in the `:root{ }` block of `_CSS`.
- **Layout / sections** — `render_html` (HTML) and `render_markdown` (plain text).

To re-skin for a different organization: change `ORG_NAME`, drop a new logo in `assets/`, and adjust
`BRAND_NAVY` / `BRAND_RED` (and the matching `--navy` / `--red` in `_CSS`). The logo is base64-embedded
at render time, so the HTML stays a single portable file; if the asset is missing, the header falls
back to a text wordmark.

The CTRL-1/CTRL-2 patterns are not defined here or in `scripts/scan.py`. They live as data in the
AppSec-owned control library, in `skills/control-library/patterns.json`, beside the judgment-control
rules in that skill's `SKILL.md`. `scripts/scan.py` loads that file at import time and compiles it into
`SECRET_PATTERNS`, `WEAK_CRYPTO_PATTERNS`, and `TLS_OFF_PATTERNS`; the report imports those same names
from `scan.py`. So the hook and the report share one definition owned by AppSec: change a pattern in the
JSON and both gates move together.

## Regenerating

```
/compliance-support:compliance-review examples/refunds-service/src/api/handlers/refund.py --report
```

The HTML opens in your browser on its own (the renderer's `--open` flag, which the command passes). Reset the example service with `bash scripts/demo_reset.sh`.

## Tests

`python -m unittest tests.test_render_report` covers the confirmatory scan, the logo fallback, and the
HTML render invariants. It uses only the standard library.
