#!/usr/bin/env python3
"""Agent eval, measure compliance-review precision/recall on labeled cases.

For each case in eval/cases.yml, run the compliance-review agent headlessly,
parse its JSON findings, and compare the set of control IDs it flags against the
expected set. Prints a per-case table plus overall precision / recall / false
positives.

The agent is an LLM, so results can vary run-to-run: this reports MEASURED numbers
for one run (no "always 100%" claim). Uses your existing Claude auth; no new creds.

Usage:  python eval/run_eval.py        (from the repo root)
"""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = Path(__file__).resolve().parent / "cases.yml"


def load_cases() -> list[dict]:
    """Tiny reader for our simple cases.yml (no YAML dependency)."""
    cases, cur = [], None
    for raw in CASES.read_text(encoding="utf-8").splitlines():
        s = raw.split("#", 1)[0].strip()   # drop inline comments
        if not s:
            continue
        if s.startswith("- file:"):
            if cur:
                cases.append(cur)
            cur = {"file": s.split(":", 1)[1].strip(), "expect": []}
        elif s.startswith("expect:") and cur is not None:
            inside = s.split(":", 1)[1].strip().strip("[]")
            cur["expect"] = [c.strip() for c in inside.split(",") if c.strip()]
    if cur:
        cases.append(cur)
    return cases


def json_objects(text: str) -> list:
    """Every top-level {...} in text that parses as JSON (brace matching)."""
    objs, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objs.append(json.loads(text[start:i + 1]))
                except json.JSONDecodeError:
                    pass
                start = None
    return objs


def review(file: str) -> set[str] | None:
    """Run the agent on one file; return the set of control IDs it flagged (None on failure)."""
    cmd = [
        "claude", "--plugin-dir", str(ROOT), "--permission-mode", "acceptEdits",
        "--allowedTools", "Read,Grep,Glob,Task,Agent", "-p",
        f"Use the compliance-review agent to review the file {file} . "
        f"Print only its JSON findings block.",
    ]
    try:
        out = subprocess.run(
            cmd, cwd=str(ROOT), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=300,
        ).stdout
    except subprocess.TimeoutExpired:
        return None
    findings = [o for o in json_objects(out) if "findings" in o]
    if not findings:
        return None
    return {f["control"] for f in findings[-1].get("findings", []) if f.get("control")}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # robust on Windows cp1252 consoles
    except Exception:
        pass
    cases = load_cases()
    print(f"Running compliance-review on {len(cases)} labeled cases (this takes a couple of minutes)...\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda c: review(c["file"]), cases))

    tp = fp = fn = 0
    rows, all_pass = [], True
    for case, got in zip(cases, results):
        exp = set(case["expect"])
        if got is None:
            rows.append((case["file"], exp, None, False))
            all_pass = False
            continue
        tp += len(exp & got)
        fp += len(got - exp)
        fn += len(exp - got)
        ok = got == exp
        all_pass = all_pass and ok
        rows.append((case["file"], exp, got, ok))

    width = max(len(Path(f).name) for f, *_ in rows)
    print(f"{'CASE':<{width}}  {'EXPECT':<15} {'GOT':<15} RESULT")
    for file, exp, got, ok in rows:
        e = ",".join(sorted(exp)) or "(clean)"
        g = "ERROR" if got is None else (",".join(sorted(got)) or "(clean)")
        print(f"{Path(file).name:<{width}}  {e:<15} {g:<15} {'PASS' if ok else 'FAIL'}")

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    print(f"\nPrecision {precision:.2f} | Recall {recall:.2f} | False positives {fp}")
    print("All cases passed." if all_pass else "Some cases failed.")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
