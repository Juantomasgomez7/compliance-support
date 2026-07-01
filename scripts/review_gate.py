#!/usr/bin/env python3
"""Compliance Support, passive review gate (Stop hook).

When Claude finishes a turn, this decides whether to nudge it to run the
compliance-review agent over the PCI-scoped files it changed. It is the Tier-2
companion to scan.py (Tier-1): scan.py blocks bad writes in real time; this
flags the two *judgment* controls (CTRL-1 PII in logs, CTRL-2 missing audit log)
at the end of the turn, once per change-set, and never blocks.

Cost discipline: if no in-scope file changed, it exits silently and no model
runs. Loop-safe via the harness `stop_hook_active` flag.

Run via review_gate.sh so the hook entry stays a .sh (fires identically on macOS
and Windows git-bash). Scope logic is reused from scan.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan import in_scope, load_scope  # noqa: E402


def changed_paths(porcelain: str) -> list[str]:
    """Repo-relative paths from `git status --porcelain` output.

    Handles staged/unstaged/untracked lines and renames (`R old -> new`, we keep
    the new path). Blank lines are ignored.
    """
    paths: list[str] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:].strip()
        if " -> " in rest:                       # a rename / copy: keep the destination
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        if rest:
            paths.append(rest)
    return paths


def in_scope_paths(paths: list[str], include: list[str], exclude: list[str]) -> list[str]:
    """Keep only the paths that are in PCI scope per .compliance.yml (reuses scan)."""
    return [p for p in paths if in_scope(p, include, exclude)]


def changeset_id(paths: list[str]) -> str:
    """A stable id for a *set* of changed files (order- and dup-independent).

    Used as the once-per-change-set sentinel: the same dirty set yields the same
    id, so we nudge once and stay quiet until the set actually changes.
    """
    key = "\n".join(sorted(set(paths)))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def already_reviewed(sentinel_path: str, cid: str) -> bool:
    """True if this exact change-set was already nudged (sentinel matches)."""
    try:
        return open(sentinel_path, encoding="utf-8").read().strip() == cid
    except OSError:
        return False


def record_reviewed(sentinel_path: str, cid: str) -> None:
    """Remember this change-set so we don't nudge for it again. Best-effort: if we
    can't write, we simply risk nudging again next turn (never an error)."""
    try:
        with open(sentinel_path, "w", encoding="utf-8") as f:
            f.write(cid)
    except OSError:
        pass


def build_reason(paths: list[str]) -> str:
    """The nudge shown to Claude when in-scope files changed (the teach channel)."""
    files = ", ".join(paths)
    return (
        f"Compliance Support: you changed PCI-scoped file(s) this turn — {files}. "
        "Before finishing, run the compliance-review agent on them and address any "
        "CTRL-1 (personal or cardholder data in logs/errors) or CTRL-2 (a money-moving "
        "action with no audit_log.record) findings. If you already reviewed them and "
        "they are clean, say so and stop."
    )


def decide(payload: dict, porcelain: str, include: list[str], exclude: list[str],
           sentinel_path: str) -> dict | None:
    """The gate's core decision. Returns a Stop `block` decision, or None to allow.

    Allows (returns None) when: this stop is already a hook-triggered continuation
    (loop guard), OR no in-scope file changed (zero model spend), OR this exact
    change-set was already nudged. Otherwise records the change-set and blocks.
    """
    if payload.get("stop_hook_active"):
        return None
    paths = in_scope_paths(changed_paths(porcelain), include, exclude)
    if not paths:
        return None
    cid = changeset_id(paths)
    if already_reviewed(sentinel_path, cid):
        return None
    record_reviewed(sentinel_path, cid)
    return {"decision": "block", "reason": build_reason(paths)}


# Per-repo, per-change-set memory. Lives inside .git (never committed, local).
SENTINEL_REL = os.path.join(".git", "compliance-review-last-changeset")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed payload -> allow the stop

    cwd = payload.get("cwd") or os.getcwd()
    include, exclude = load_scope(os.path.join(cwd, ".compliance.yml"))
    if not include:
        return  # no scope defined -> nothing to gate

    try:
        porcelain = subprocess.run(
            # --untracked-files=all so new files are listed individually rather
            # than collapsed to a bare directory (which would lose scope precision).
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=cwd,
            capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return  # git unavailable -> fail open, never block the stop

    decision = decide(payload, porcelain, include, exclude,
                      os.path.join(cwd, SENTINEL_REL))
    if decision:
        print(json.dumps(decision))


if __name__ == "__main__":
    main()
