#!/usr/bin/env python3
"""Render a compliance report (Markdown and HTML) from compliance-review findings.

Reads a JSON array of per-file results on stdin, or from a file given as the first
argument. Each result has the shape the compliance-review agent emits:

    {"file": "...", "in_scope": true, "findings": [
        {"control": "CTRL-1", "line": 19, "evidence": "...", "fix": "..."}
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
        "name": "PII or cardholder data in logs or errors",
        "maps_to": "PCI Req 3 & 10, GDPR Art 5 & 32",
        "why": "Logs are widely readable and long retained, and are often shipped outside the "
               "cardholder-data environment. A full card number or personal data there spreads "
               "regulated data into places that were never assessed for it.",
        "kind": "review",
        "fix": "Log a non-sensitive identifier (account or refund id) instead of the raw value.",
    },
    "CTRL-2": {
        "name": "Money-moving action without an audit-log entry",
        "maps_to": "SOC 2 CC7.2, PCI Req 10",
        "why": "Every action that moves money needs a who-did-what-when trail. Without one there is no "
               "way to detect, investigate, or attribute a mistaken or fraudulent action after the fact.",
        "kind": "review",
        "fix": "Call audit_log.record(...) after the action succeeds, with non-sensitive metadata only.",
    },
    "CTRL-3": {
        "name": "Hardcoded secret or credential",
        "maps_to": "PCI Req 8",
        "why": "A secret in source is exposed to everyone with repository access and is hard to rotate. "
               "It belongs in the environment or a secrets manager.",
        "kind": "block",
        "fix": "Read it from the environment, e.g. os.environ['PROCESSOR_API_KEY'].",
    },
    "CTRL-4": {
        "name": "Weak cryptography or disabled transport security",
        "maps_to": "PCI Req 3 & 4, SOC 2 CC6.7",
        "why": "Broken algorithms and disabled TLS verification leave data readable or alterable in "
               "transit or at rest.",
        "kind": "block",
        "fix": "Use a strong primitive (bcrypt / AES-GCM) and keep TLS verification on.",
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
    "CTRL-1": "Personal or card data ending up in logs or error messages",
    "CTRL-2": "Money-moving actions that leave no audit trail",
    "CTRL-3": "Passwords / API keys written directly into the source code",
    "CTRL-4": "Weak encryption, or TLS certificate checking turned off",
}


# --- Confirmatory scan (CTRL-3 / CTRL-4) --------------------------------------
# A point-in-time re-check of the reviewed files for the two deterministic controls
# the pre-write hook enforces, reusing the hook's exact patterns (imported above).
# The hook blocks these at write time; this confirms the files on disk are clean and
# catches anything introduced outside Claude Code (bypassing the hook).
def scan_content(content: str) -> list[dict]:
    """Per-line CTRL-3 / CTRL-4 hits in one file's text.

    Returns findings shaped like the agent's: {control, line, evidence, fix}. Per-line
    matching mirrors the hook's whole-content patterns and yields a line number.
    """
    hits: list[dict] = []
    for n, line in enumerate(content.splitlines(), start=1):
        if any(p.search(line) for p in SECRET_PATTERNS):
            hits.append({"control": "CTRL-3", "line": n,
                         "evidence": line.strip(), "fix": CONTROLS["CTRL-3"]["fix"]})
        if any(p.search(line) for p in (*WEAK_CRYPTO_PATTERNS, *TLS_OFF_PATTERNS)):
            hits.append({"control": "CTRL-4", "line": n,
                         "evidence": line.strip(), "fix": CONTROLS["CTRL-4"]["fix"]})
    return hits


def confirmatory_findings(files: list[str]) -> tuple[list[dict], int]:
    """Scan each readable file for CTRL-3/CTRL-4. Returns (findings, files_scanned)."""
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


# --- Markdown ----------------------------------------------------------------
def render_markdown(findings, clean) -> str:
    counts = control_counts(findings)
    reviewed = len({f["file"] for f in findings} | set(clean))
    out = [
        "# Compliance review report",
        f"_Compliance Support, {date.today().isoformat()}, flag for review, not audit-grade_",
        "",
        "## Summary",
        f"- Files reviewed: {reviewed}  |  Findings: {len(findings)}  |  Clean: {len(clean)}",
        "- By control: " + (", ".join(f"{c} x{n}" for c, n in sorted(counts.items())) or "none"),
        "",
        "## Findings",
    ]
    if not findings:
        out.append("None. Every reviewed file was clean.")
    by_file: dict[str, list] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)
    for file, items in by_file.items():
        out.append(f"### `{file}`")
        for f in items:
            c = CONTROLS.get(f["control"], _UNKNOWN)
            line = f" line {f['line']}" if f.get("line") is not None else ""
            out.append(f"- **{f['control']}: {c['name']}** ({c['maps_to']}){line}")
            out.append(f"  - What: `{f['evidence']}`")
            out.append(f"  - Why it matters: {c['why']}")
            out.append(f"  - Fix: {f['fix']}")
        out.append("")
    out.append("## Reviewed and clean")
    out.append(", ".join(f"`{c}`" for c in clean) if clean else "None.")
    out += ["", "---", "_Flag for review. Suggestions for an engineer to apply, not an auditor's sign-off._"]
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
    """One row of the 'Controls checked' table: id, what it guards, how, this-run status."""
    c = CONTROLS.get(cid, _UNKNOWN)
    kind = c["kind"]
    if kind == "review":
        n = review_counts.get(cid, 0)
        status = (f"<span class='status warn'>{n} to review</span>" if n
                  else "<span class='status ok'>No issues</span>")
    else:
        n = block_counts.get(cid, 0)
        plural = "s" if files_scanned != 1 else ""
        status = (f"<span class='status bad'>{n} found</span>" if n
                  else f"<span class='status ok'>Clean &middot; {files_scanned} file{plural} scanned</span>")
    return (f"<tr><td class=id>{_esc(cid)}</td>"
            f"<td>{_esc(GUARD_AGAINST.get(cid, c['name']))}</td>"
            f"<td>{_esc(HOW_CHECKED[kind])}</td>"
            f"<td>{status}</td></tr>")


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

    if total == 0:
        banner = ("ok", "&#10003;",
                  f"All clear &mdash; {reviewed} file{'s' if reviewed != 1 else ''} reviewed, "
                  "no issues found.")
    elif confirm_findings:
        banner = ("bad", "&#9888;",
                  f"{total} issue{'s' if total != 1 else ''} need attention, "
                  "including an auto-blocked control.")
    else:
        banner = ("warn", "&#9888;",
                  f"{total} issue{'s' if total != 1 else ''} need your review.")

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
        "<th>How it's checked</th><th>This run</th></tr>",
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
        "<dt>PCI DSS &middot; SOC 2 &middot; GDPR</dt><dd>The data-protection standards these checks map "
        "to: card-data security (PCI DSS), service security controls (SOC 2), and personal-data "
        "protection (GDPR).</dd>"
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
    open("compliance-report.md", "w", encoding="utf-8").write(render_markdown(findings, clean))
    open("compliance-report.html", "w", encoding="utf-8").write(
        render_html(findings, clean, confirm, scanned))
    print("Wrote compliance-report.md and compliance-report.html")


if __name__ == "__main__":
    main()
