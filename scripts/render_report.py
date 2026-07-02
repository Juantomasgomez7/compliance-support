#!/usr/bin/env python3
"""Render a compliance report (Markdown and HTML) from compliance-review findings.

Reads a JSON array of per-file results on stdin, or from a file given as the first
argument. Each result has the shape the compliance-review agent emits:

    {"file": "...", "in_scope": true, "findings": [
        {"control": "CTRL-3", "line": 19, "evidence": "...", "fix": "..."}
    ]}

Writes compliance-report.md and compliance-report.html at the repo root. The agent
supplies the per-finding specifics; this script supplies the control name, the
mapping, and the "why it matters" text, so the report reads the same every time.
"""
from __future__ import annotations

import base64
import html
import json
import os
import sys
from datetime import date

# Make scan.py importable regardless of the working directory (it sits beside this file).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan import SECRET_PATTERNS, WEAK_CRYPTO_PATTERNS, TLS_OFF_PATTERNS  # noqa: E402

# --- Branding (Capital One) ---------------------------------------------------
BRAND_NAVY = "#004977"
BRAND_RED = "#c8102e"
ORG_NAME = "Capital One"
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets",
                         "capital-one-logo.png")

CONTROLS = {
    "CTRL-1": {
        "name": "Hardcoded secret or credential",
        "maps_to": "PCI Req 8",
        "why": "A secret in source is exposed to everyone with repository access and is hard to rotate. "
               "It belongs in the environment or a secrets manager.",
        "kind": "block",
        "fix": "Read it from the environment, e.g. os.environ['PROCESSOR_API_KEY'].",
    },
    "CTRL-2": {
        "name": "Weak cryptography or disabled transport security",
        "maps_to": "PCI Req 3 & 4, SOC 2 CC6.7",
        "why": "Broken algorithms and disabled TLS verification leave data readable or alterable in "
               "transit or at rest.",
        "kind": "block",
        "fix": "Use a strong primitive (bcrypt / AES-GCM) and keep TLS verification on.",
    },
    "CTRL-3": {
        "name": "PII or cardholder data in logs or errors",
        "maps_to": "PCI Req 3 & 10, GDPR Art 5 & 32",
        "why": "Logs are widely readable and long retained, and are often shipped outside the "
               "cardholder-data environment. A full card number or personal data there spreads "
               "regulated data into places that were never assessed for it.",
        "kind": "review",
        "fix": "Log a non-sensitive identifier (account or refund id) instead of the raw value.",
    },
    "CTRL-4": {
        "name": "Money-moving action without an audit-log entry",
        "maps_to": "SOC 2 CC7.2, PCI Req 10",
        "why": "Every action that moves money needs a who-did-what-when trail. Without one there is no "
               "way to detect, investigate, or attribute a mistaken or fraudulent action after the fact.",
        "kind": "review",
        "fix": "Call audit_log.record(...) after the action succeeds, with non-sensitive metadata only.",
    },
}
_UNKNOWN = {"name": "Unknown control", "maps_to": "", "why": "", "kind": "review", "fix": ""}

# Plain-language labels for a non-security reader (HTML report only).
KIND_LABEL = {"review": "Needs review", "block": "Auto-blocked"}
HOW_CHECKED = {
    "review": "AI review of changed code",
    "block": "Automatic gate (blocks the save) + confirmation scan",
}
GUARD_AGAINST = {
    "CTRL-1": "Passwords / API keys written directly into the source code",
    "CTRL-2": "Weak encryption, or TLS certificate checking turned off",
    "CTRL-3": "Personal or card data ending up in logs or error messages",
    "CTRL-4": "Money-moving actions that leave no audit trail",
}

# The actual standard clauses the controls map to, in plain terms (family level, matching
# the control library's citation convention). Surfaced in the "What we check against" section.
STANDARDS = [
    ("PCI DSS — Requirement 3",
     "Protect stored cardholder data (e.g. keep full card numbers out of logs)."),
    ("PCI DSS — Requirement 4",
     "Protect cardholder data with strong cryptography when it travels over open, public networks."),
    ("PCI DSS — Requirement 8",
     "Identify and authenticate access to systems; no shared or hardcoded credentials."),
    ("PCI DSS — Requirement 10",
     "Log and monitor all access to system components and cardholder data."),
    ("SOC 2 — CC6.7 (Trust Services Criteria)",
     "Protect data while it is being transmitted (encryption in transit)."),
    ("SOC 2 — CC7.2 (Trust Services Criteria)",
     "Monitor systems for anomalies and security events."),
    ("GDPR — Article 5",
     "Principles for processing personal data, including integrity and confidentiality."),
    ("GDPR — Article 32",
     "Security of processing: appropriate technical measures to protect personal data."),
]


# --- Confirmatory scan (CTRL-1 / CTRL-2) --------------------------------------
# A point-in-time re-check of the reviewed files for the two deterministic controls
# the pre-write hook enforces, reusing the hook's exact patterns (imported above).
# The hook blocks these at write time; this confirms the files on disk are clean and
# catches anything introduced outside Claude Code (bypassing the hook).
def scan_content(content: str) -> list[dict]:
    """Per-line CTRL-1 / CTRL-2 hits in one file's text.

    Returns findings shaped like the agent's: {control, line, evidence, fix}. Per-line
    matching mirrors the hook's whole-content patterns and yields a line number.
    """
    hits: list[dict] = []
    for n, line in enumerate(content.splitlines(), start=1):
        if any(p.search(line) for p in SECRET_PATTERNS):
            hits.append({"control": "CTRL-1", "line": n,
                         "evidence": line.strip(), "fix": CONTROLS["CTRL-1"]["fix"]})
        if any(p.search(line) for p in (*WEAK_CRYPTO_PATTERNS, *TLS_OFF_PATTERNS)):
            hits.append({"control": "CTRL-2", "line": n,
                         "evidence": line.strip(), "fix": CONTROLS["CTRL-2"]["fix"]})
    return hits


def confirmatory_findings(files: list[str]) -> tuple[list[dict], int]:
    """Scan each readable file for CTRL-1/CTRL-2. Returns (findings, files_scanned)."""
    findings: list[dict] = []
    scanned = 0
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue  # not readable from here -> skip, never crash the render
        scanned += 1
        for hit in scan_content(content):
            findings.append({"file": path, **hit})
    return findings, scanned


def load_results() -> list:
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    data = json.loads(raw)
    return data["results"] if isinstance(data, dict) else data


def collect(results: list):
    """Split per-file results into a flat findings list and a list of clean files."""
    findings, clean = [], []
    for r in results:
        if not r.get("in_scope", True):
            continue
        items = r.get("findings") or []
        if not items:
            clean.append(r["file"])
            continue
        for f in items:
            findings.append({
                "file": r["file"],
                "control": f.get("control", ""),
                "line": f.get("line"),
                "evidence": f.get("evidence", ""),
                "fix": f.get("fix", ""),
            })
    return findings, clean


def control_counts(findings: list) -> dict:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["control"]] = counts.get(f["control"], 0) + 1
    return counts


def _s(n: int) -> str:
    """Pluralize a noun: '' for one, 's' otherwise."""
    return "" if n == 1 else "s"


def _verdict(reviewed: int, total: int, has_block: bool) -> tuple[str, str]:
    """Overall verdict shared by both reports: (kind, plain message). kind in ok|warn|bad."""
    if total == 0:
        return "ok", f"All clear — {reviewed} file{_s(reviewed)} reviewed, no issues found."
    if has_block:
        return "bad", f"{total} issue{_s(total)} need attention, including an auto-blocked control."
    return "warn", f"{total} issue{_s(total)} need your review."


def _coverage_status(cid, review_counts, block_counts, files_scanned) -> tuple[str, str]:
    """One control's 'this run' status, shared by both reports: (plain text, kind)."""
    kind = CONTROLS.get(cid, _UNKNOWN)["kind"]
    if kind == "review":
        n = review_counts.get(cid, 0)
        return (f"{n} to review", "warn") if n else ("No issues", "ok")
    n = block_counts.get(cid, 0)
    if n:
        return f"{n} found", "bad"
    return f"Clean · {files_scanned} file{_s(files_scanned)} scanned", "ok"


# --- Markdown ----------------------------------------------------------------
def render_markdown(findings, clean, confirm_findings, files_scanned) -> str:
    """Plain-text report. Same content as the HTML, minus the logo and colours."""
    review_counts = control_counts(findings)
    block_counts = control_counts(confirm_findings)
    reviewed = len({f["file"] for f in findings} | set(clean))
    all_findings = findings + confirm_findings
    total = len(all_findings)
    today = date.today().isoformat()
    _, verdict_msg = _verdict(reviewed, total, bool(confirm_findings))

    out = [
        "# Data-Protection Compliance Review",
        f"_Compliance Support · {today} · flag for review, not an audit sign-off_",
        "",
        f"Compliance Support is an automated data-protection gate for code in {ORG_NAME}'s PCI "
        "cardholder-data environment. It checks changed code against four controls and flags anything "
        "that needs an engineer's attention. This is a flag-for-review helper, not an auditor's sign-off.",
        "",
        f"This report covers the {reviewed} in-scope file{_s(reviewed)} reviewed on {today}.",
        "",
        f"**{verdict_msg}**",
        "",
        f"- Files reviewed: {reviewed}  |  Issues to address: {total}  |  Clean files: {len(clean)}",
        "",
        "## Controls checked",
        "",
        "| Control | What it guards against | Standards | How it's checked | This run |",
        "| --- | --- | --- | --- | --- |",
    ]
    for cid in ("CTRL-1", "CTRL-2", "CTRL-3", "CTRL-4"):
        c = CONTROLS[cid]
        status_text, _kind = _coverage_status(cid, review_counts, block_counts, files_scanned)
        out.append(f"| {cid} | {GUARD_AGAINST.get(cid, c['name'])} | {c['maps_to']} | "
                   f"{HOW_CHECKED[c['kind']]} | {status_text} |")

    out += ["", "## What we found", ""]
    if not all_findings:
        out.append("Nothing to address. Every reviewed file was clean.")
    else:
        by_file: dict[str, list] = {}
        for f in all_findings:
            by_file.setdefault(f["file"], []).append(f)
        for file, items in by_file.items():
            out.append(f"### `{file}`")
            for f in items:
                c = CONTROLS.get(f["control"], _UNKNOWN)
                line = f" · line {f['line']}" if f.get("line") is not None else ""
                fix = f.get("fix") or c["fix"]
                out.append(f"- **{f['control']}: {c['name']}** ({KIND_LABEL[c['kind']]})")
                out.append(f"  - Standards: {c['maps_to']}{line}")
                out.append(f"  - What we saw: `{f['evidence']}`")
                out.append(f"  - Why it matters: {c['why']}")
                out.append(f"  - What to do: {fix}")
            out.append("")

    out += ["## Reviewed and clean", ""]
    out.append(", ".join(f"`{c}`" for c in clean) if clean else "None.")

    out += ["", "## What we check against", ""]
    for clause, meaning in STANDARDS:
        out.append(f"- **{clause}** — {meaning}")
    out += [
        "",
        "_Source frameworks: PCI DSS (card-data security), SOC 2 Trust Services Criteria (service "
        "controls), and GDPR (EU personal-data protection). Citations are at the standard-family level, "
        "matching the control library — not specific sub-requirements._",
        "",
        "## How to read this report",
        "",
        "- **PCI scope** — the parts of the codebase that handle card or customer data. Only these files "
        "are checked.",
        "- **Flag for review** — suggestions for an engineer to apply. The gate does not edit your code "
        "and is not an auditor's sign-off.",
        "- **Needs review** — a person should look: the code may expose data or skip an audit step.",
        "- **Auto-blocked** — the gate stops these the moment you save; this report re-scans the saved "
        "files and flags any that got in another way.",
        "",
        "---",
        f"_Flag for review, not an auditor's sign-off. Generated by Compliance Support for {ORG_NAME}._",
    ]
    return "\n".join(out) + "\n"


# --- HTML --------------------------------------------------------------------
_CSS = """
:root{
  --navy:#004977; --red:#c8102e; --ink:#1a1f29; --muted:#5b6573; --line:#e4e7ec;
  --review:#b45309; --block:#c8102e; --ok:#15803d; --bg:#f4f6f8; --soft:#f7f9fb;
}
*{box-sizing:border-box;}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);
  background:var(--bg);margin:0;padding:32px;line-height:1.55;}
.page{max-width:860px;margin:0 auto;background:#fff;border:1px solid var(--line);
  border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(16,24,40,.04);}
.head{display:flex;align-items:center;gap:20px;padding:24px 36px 18px;}
.head .logo{height:42px;width:auto;display:block;}
.head .wordmark{font-weight:800;font-size:22px;color:var(--navy);letter-spacing:-.02em;}
.head .divider{width:1px;align-self:stretch;background:var(--line);margin:2px 0;}
.head h1{font-size:20px;margin:0;color:var(--navy);letter-spacing:-.01em;}
.head .meta{color:var(--muted);font-size:12.5px;margin:3px 0 0;}
.rule{height:3px;background:linear-gradient(90deg,var(--navy),var(--red));}
.body{padding:26px 36px 30px;}
.lead{font-size:14px;margin:0 0 22px;}
.lead .muted{color:var(--muted);}
.scope{font-size:12.5px;color:var(--muted);margin:0 0 12px;}
.banner{border-radius:10px;padding:14px 16px;font-size:15px;font-weight:600;margin:0 0 16px;
  border:1px solid var(--line);display:flex;align-items:center;gap:10px;}
.banner.ok{background:#f0fdf4;border-color:#bbf7d0;color:var(--ok);}
.banner.warn{background:#fffbeb;border-color:#fde68a;color:#92400e;}
.banner.bad{background:#fef2f2;border-color:#fecaca;color:var(--red);}
.banner .dot{font-size:18px;line-height:1;}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 26px;}
.chip{background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:8px 13px;
  font-size:13px;color:var(--muted);}
.chip b{font-size:16px;color:var(--navy);margin-right:5px;}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--navy);
  border-bottom:2px solid var(--line);padding-bottom:7px;margin:30px 0 14px;}
h2 .hint{text-transform:none;letter-spacing:0;font-weight:400;color:var(--muted);font-size:12px;
  margin-left:8px;}
table.cov{width:100%;border-collapse:collapse;font-size:13px;}
table.cov th{text-align:left;color:var(--muted);font-weight:600;font-size:11.5px;
  text-transform:uppercase;letter-spacing:.03em;padding:0 10px 8px;border-bottom:1px solid var(--line);}
table.cov td{padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top;}
table.cov .id{font-weight:700;color:var(--navy);white-space:nowrap;}
table.cov .std{color:var(--muted);font-size:12px;}
.status{font-weight:600;white-space:nowrap;}
.status.ok{color:var(--ok);} .status.warn{color:var(--review);} .status.bad{color:var(--red);}
.file{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px;color:var(--muted);
  margin:20px 0 8px;}
.card{border:1px solid var(--line);border-left-width:4px;border-radius:9px;padding:15px 17px;
  margin:10px 0;background:#fff;}
.card.review{border-left-color:var(--review);}
.card.block{border-left-color:var(--block);}
.ctrl{font-weight:700;color:var(--ink);}
.tag{font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;margin-left:9px;
  vertical-align:middle;color:#fff;letter-spacing:.02em;}
.tag.review{background:var(--review);}
.tag.block{background:var(--block);}
.map{color:var(--muted);font-size:11.5px;margin:3px 0 11px;}
.row{margin:7px 0;font-size:13.5px;}
.row .label{display:inline-block;min-width:96px;color:var(--muted);font-weight:600;}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12.5px;background:var(--soft);
  border:1px solid var(--line);border-radius:5px;padding:1px 6px;}
.allclear{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px 18px;
  color:var(--ok);font-weight:600;}
ul.clean{margin:6px 0 0;padding:0;}
ul.clean li{color:var(--ok);font-size:13.5px;list-style:none;padding:3px 0;
  font-family:ui-monospace,SFMono-Regular,Consolas,monospace;}
ul.clean li:before{content:"\\2713";font-weight:800;margin-right:9px;}
.gloss{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:16px 18px;
  margin-top:8px;}
.gloss dt{font-weight:700;color:var(--navy);font-size:13px;margin-top:10px;}
.gloss dt:first-child{margin-top:0;}
.gloss dd{margin:2px 0 0;font-size:13px;}
.foot{color:var(--muted);font-size:12px;border-top:1px solid var(--line);margin-top:28px;padding-top:14px;}
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def logo_tag() -> str:
    """Base64-embed the bundled logo so the HTML is a single portable file.

    Falls back to a navy text wordmark if the asset is missing, so render never breaks.
    """
    try:
        with open(LOGO_PATH, "rb") as fh:
            data = base64.b64encode(fh.read()).decode("ascii")
        return f"<img class=logo alt='{_esc(ORG_NAME)}' src='data:image/png;base64,{data}'>"
    except OSError:
        return f"<span class=wordmark>{_esc(ORG_NAME)}</span>"


def _coverage_row(cid, review_counts, block_counts, files_scanned) -> str:
    """One row of the 'Controls checked' table: id, what it guards, standards, how, status."""
    c = CONTROLS.get(cid, _UNKNOWN)
    text, kind_cls = _coverage_status(cid, review_counts, block_counts, files_scanned)
    return (f"<tr><td class=id>{_esc(cid)}</td>"
            f"<td>{_esc(GUARD_AGAINST.get(cid, c['name']))}</td>"
            f"<td class=std>{_esc(c['maps_to'])}</td>"
            f"<td>{_esc(HOW_CHECKED[c['kind']])}</td>"
            f"<td><span class='status {kind_cls}'>{_esc(text)}</span></td></tr>")


def _finding_card(f) -> str:
    """One finding rendered for a non-expert: what we saw, why it matters, what to do."""
    c = CONTROLS.get(f["control"], _UNKNOWN)
    kind = c["kind"]
    line = f" &middot; line {_esc(f['line'])}" if f.get("line") is not None else ""
    fix = f.get("fix") or c["fix"]
    return (
        f"<div class='card {kind}'>"
        f"<div><span class=ctrl>{_esc(f['control'])}: {_esc(c['name'])}</span>"
        f"<span class='tag {kind}'>{_esc(KIND_LABEL[kind])}</span></div>"
        f"<div class=map>Standards: {_esc(c['maps_to'])}{line}</div>"
        f"<div class=row><span class=label>What we saw</span><code>{_esc(f['evidence'])}</code></div>"
        f"<div class=row><span class=label>Why it matters</span>{_esc(c['why'])}</div>"
        f"<div class=row><span class=label>What to do</span>{_esc(fix)}</div>"
        f"</div>"
    )


def render_html(findings, clean, confirm_findings, files_scanned) -> str:
    review_counts = control_counts(findings)
    block_counts = control_counts(confirm_findings)
    reviewed = len({f["file"] for f in findings} | set(clean))
    all_findings = findings + confirm_findings
    total = len(all_findings)
    today = date.today().isoformat()

    kind, verdict_msg = _verdict(reviewed, total, bool(confirm_findings))
    icon = "&#10003;" if kind == "ok" else "&#9888;"
    banner = (kind, icon, verdict_msg)

    p = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        "<meta name=viewport content='width=device-width,initial-scale=1'>",
        "<title>Data-Protection Compliance Review</title><style>", _CSS,
        "</style></head><body><div class=page>",
        "<div class=head>", logo_tag(), "<div class=divider></div>",
        "<div><h1>Data-Protection Compliance Review</h1>",
        f"<p class=meta>Compliance Support &middot; {today} &middot; "
        "flag for review, not an audit sign-off</p></div></div>",
        "<div class=rule></div><div class=body>",
        f"<p class=lead>Compliance Support is an automated data-protection gate for code in "
        f"{_esc(ORG_NAME)}'s PCI cardholder-data environment. It checks changed code against four "
        f"controls and flags anything that needs an engineer's attention. "
        f"<span class=muted>This is a flag-for-review helper &mdash; suggestions to apply, not an "
        f"auditor's sign-off.</span></p>",
        f"<p class=scope>This report covers the {reviewed} in-scope file"
        f"{'s' if reviewed != 1 else ''} reviewed on {today}.</p>",
        f"<div class='banner {banner[0]}'><span class=dot>{banner[1]}</span>"
        f"<span>{banner[2]}</span></div>",
        "<div class=stats>",
        f"<span class=chip><b>{reviewed}</b>files reviewed</span>",
        f"<span class=chip><b>{total}</b>issue{'s' if total != 1 else ''} to address</span>",
        f"<span class=chip><b>{len(clean)}</b>clean file{'s' if len(clean) != 1 else ''}</span>",
        "</div>",
        "<h2>Controls checked<span class=hint>what this gate looks for, and how each is "
        "enforced</span></h2>",
        "<table class=cov><tr><th>Control</th><th>What it guards against</th>"
        "<th>Standards</th><th>How it's checked</th><th>This run</th></tr>",
    ]
    for cid in ("CTRL-1", "CTRL-2", "CTRL-3", "CTRL-4"):
        p.append(_coverage_row(cid, review_counts, block_counts, files_scanned))
    p.append("</table>")

    p.append("<h2>What we found</h2>")
    if not all_findings:
        p.append("<div class=allclear>&#10003; Nothing to address. Every reviewed file was clean.</div>")
    else:
        by_file: dict[str, list] = {}
        for f in all_findings:
            by_file.setdefault(f["file"], []).append(f)
        for file, items in by_file.items():
            p.append(f"<div class=file>{_esc(file)}</div>")
            for f in items:
                p.append(_finding_card(f))

    p.append("<h2>Reviewed &amp; clean</h2>")
    if clean:
        p.append("<ul class=clean>" + "".join(f"<li>{_esc(c)}</li>" for c in clean) + "</ul>")
    else:
        p.append("<p class=lead>None.</p>")

    p.append("<h2>What we check against<span class=hint>the standards these controls map to</span></h2>")
    p.append("<dl class=gloss>")
    for clause, meaning in STANDARDS:
        p.append(f"<dt>{_esc(clause)}</dt><dd>{_esc(meaning)}</dd>")
    p.append("</dl>")
    p.append("<p class=scope>Source frameworks: PCI DSS (card-data security), SOC 2 Trust Services "
             "Criteria (service controls), and GDPR (EU personal-data protection). Citations are at the "
             "standard-family level, matching the control library &mdash; not specific sub-requirements.</p>")

    p.append("<h2>How to read this report<span class=hint>plain-English definitions</span></h2>")
    p.append(
        "<dl class=gloss>"
        "<dt>PCI scope</dt><dd>The parts of the codebase that handle card or customer data. Only these "
        "files are checked; everything else is left alone on purpose.</dd>"
        "<dt>Flag for review</dt><dd>These are suggestions for an engineer to apply. The gate does not "
        "edit your code and is not an auditor's sign-off.</dd>"
        "<dt>Needs review (amber)</dt><dd>A person should look: the code may expose data or skip an audit "
        "step. Surfaced by an AI review of your changes.</dd>"
        "<dt>Auto-blocked (red)</dt><dd>The gate stops these the moment you save, so they cannot enter "
        "scoped code. This report re-scans the saved files and flags any that got in another way.</dd>"
        "</dl>"
    )
    p.append(f"<p class=foot>Flag for review, not an auditor's sign-off. "
             f"Generated by Compliance Support for {_esc(ORG_NAME)}.</p>")
    p.append("</div></div></body></html>")
    return "\n".join(p)


def main() -> None:
    results = load_results()
    findings, clean = collect(results)
    inscope_files = [r["file"] for r in results if r.get("in_scope", True)]
    confirm, scanned = confirmatory_findings(inscope_files)
    open("compliance-report.md", "w", encoding="utf-8").write(
        render_markdown(findings, clean, confirm, scanned))
    open("compliance-report.html", "w", encoding="utf-8").write(
        render_html(findings, clean, confirm, scanned))
    print("Wrote compliance-report.md and compliance-report.html")


if __name__ == "__main__":
    main()
