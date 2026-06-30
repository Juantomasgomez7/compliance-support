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

import html
import json
import sys
from datetime import date

CONTROLS = {
    "CTRL-1": {
        "name": "PII or cardholder data in logs or errors",
        "maps_to": "PCI Req 3 & 10, GDPR Art 5 & 32",
        "why": "Logs are widely readable and long retained, and are often shipped outside the "
               "cardholder-data environment. A full card number or personal data there spreads "
               "regulated data into places that were never assessed for it.",
        "kind": "review",
    },
    "CTRL-2": {
        "name": "Money-moving action without an audit-log entry",
        "maps_to": "SOC 2 CC7.2, PCI Req 10",
        "why": "Every action that moves money needs a who-did-what-when trail. Without one there is no "
               "way to detect, investigate, or attribute a mistaken or fraudulent action after the fact.",
        "kind": "review",
    },
    "CTRL-3": {
        "name": "Hardcoded secret or credential",
        "maps_to": "PCI Req 8",
        "why": "A secret in source is exposed to everyone with repository access and is hard to rotate. "
               "It belongs in the environment or a secrets manager.",
        "kind": "block",
    },
    "CTRL-4": {
        "name": "Weak cryptography or disabled transport security",
        "maps_to": "PCI Req 3 & 4, SOC 2 CC6.7",
        "why": "Broken algorithms and disabled TLS verification leave data readable or alterable in "
               "transit or at rest.",
        "kind": "block",
    },
}
_UNKNOWN = {"name": "Unknown control", "maps_to": "", "why": "", "kind": "review"}


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
:root{--ink:#1a1a1a;--muted:#6b7280;--line:#e5e7eb;--review:#d97706;--block:#dc2626;--ok:#16a34a;}
*{box-sizing:border-box;}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);
  background:#f6f7f9;margin:0;padding:32px;line-height:1.5;}
.page{max-width:820px;margin:0 auto;background:#fff;border:1px solid var(--line);border-radius:12px;
  padding:32px 36px;}
h1{font-size:22px;margin:0 0 4px;}
.meta{color:var(--muted);font-size:13px;margin:0 0 20px;}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 24px;}
.chip{background:#f3f4f6;border:1px solid var(--line);border-radius:8px;padding:6px 12px;font-size:13px;}
.chip b{font-size:15px;}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);
  border-bottom:1px solid var(--line);padding-bottom:6px;margin:28px 0 14px;}
.file{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px;color:var(--muted);
  margin:18px 0 8px;}
.card{border:1px solid var(--line);border-left-width:4px;border-radius:8px;padding:14px 16px;margin:10px 0;}
.card.review{border-left-color:var(--review);}
.card.block{border-left-color:var(--block);}
.ctrl{font-weight:600;}
.tag{font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;margin-left:8px;
  vertical-align:middle;color:#fff;}
.tag.review{background:var(--review);}
.tag.block{background:var(--block);}
.map{color:var(--muted);font-size:12px;margin:2px 0 10px;}
.row{margin:6px 0;font-size:14px;}
.row .label{color:var(--muted);font-weight:600;margin-right:6px;}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12.5px;background:#f3f4f6;
  border:1px solid var(--line);border-radius:5px;padding:1px 6px;}
.clean li{color:var(--ok);font-size:14px;list-style:none;}
.clean li:before{content:"\\2713  ";font-weight:700;}
.foot{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);margin-top:26px;padding-top:14px;}
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def render_html(findings, clean) -> str:
    counts = control_counts(findings)
    reviewed = len({f["file"] for f in findings} | set(clean))
    parts = [f"<!doctype html><html lang=en><head><meta charset=utf-8>",
             "<title>Compliance review report</title><style>", _CSS, "</style></head><body><div class=page>",
             "<h1>Compliance review report</h1>",
             f"<p class=meta>Compliance Support &middot; {date.today().isoformat()} &middot; "
             "flag for review, not an audit sign-off</p>",
             "<div class=stats>",
             f"<span class=chip><b>{reviewed}</b> files reviewed</span>",
             f"<span class=chip><b>{len(findings)}</b> findings</span>",
             f"<span class=chip><b>{len(clean)}</b> clean</span>"]
    for c, n in sorted(counts.items()):
        parts.append(f"<span class=chip>{_esc(c)} <b>x{n}</b></span>")
    parts.append("</div>")

    parts.append("<h2>Findings</h2>")
    if not findings:
        parts.append("<p>None. Every reviewed file was clean.</p>")
    by_file: dict[str, list] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)
    for file, items in by_file.items():
        parts.append(f"<div class=file>{_esc(file)}</div>")
        for f in items:
            c = CONTROLS.get(f["control"], _UNKNOWN)
            kind = c["kind"]
            line = f" &middot; line {_esc(f['line'])}" if f.get("line") is not None else ""
            parts.append(f"<div class='card {kind}'>")
            parts.append(f"<div><span class=ctrl>{_esc(f['control'])}: {_esc(c['name'])}</span>"
                         f"<span class='tag {kind}'>{kind}</span></div>")
            parts.append(f"<div class=map>{_esc(c['maps_to'])}{line}</div>")
            parts.append(f"<div class=row><span class=label>What</span><code>{_esc(f['evidence'])}</code></div>")
            parts.append(f"<div class=row><span class=label>Why it matters</span>{_esc(c['why'])}</div>")
            parts.append(f"<div class=row><span class=label>Fix</span>{_esc(f['fix'])}</div>")
            parts.append("</div>")

    parts.append("<h2>Reviewed and clean</h2>")
    if clean:
        parts.append("<ul class=clean>" + "".join(f"<li>{_esc(c)}</li>" for c in clean) + "</ul>")
    else:
        parts.append("<p>None.</p>")
    parts.append("<p class=foot>Flag for review. These are suggestions for an engineer to apply, "
                 "not an auditor's sign-off.</p>")
    parts.append("</div></body></html>")
    return "\n".join(parts)


def main() -> None:
    findings, clean = collect(load_results())
    open("compliance-report.md", "w", encoding="utf-8").write(render_markdown(findings, clean))
    open("compliance-report.html", "w", encoding="utf-8").write(render_html(findings, clean))
    print("Wrote compliance-report.md and compliance-report.html")


if __name__ == "__main__":
    main()
