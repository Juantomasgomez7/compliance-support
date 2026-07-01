#!/usr/bin/env python3
"""Compliance Support, deterministic pre-write scan (PreToolUse: Write|Edit).

Reads the hook payload from stdin. If the PENDING write lands in an in-scope
(PCI) path defined by .compliance.yml AND the content contains a hardcoded
secret (CTRL-3) or weak crypto / disabled TLS (CTRL-4), it blocks the write and
explains the control + the fix. Otherwise it stays silent and the write proceeds.

No model, no network: a fast, deterministic gate. Run via scan.sh so the hook
entry stays a .sh (fires identically on macOS and Windows git-bash).
"""
from __future__ import annotations

import json
import os
import re
import sys

# --- Control definitions (AppSec-owned) --------------------------------------
# The deterministic CTRL-3/CTRL-4 patterns are NOT defined here. AppSec owns
# every control definition; they live beside the control library's SKILL.md.
# Engineering owns only this loader. Resolved relative to __file__ so the
# working directory never matters (the hook and render_report both import this).
_PATTERNS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "skills", "control-library", "patterns.json",
)


def load_patterns(path: str) -> dict:
    """Read the AppSec-owned control patterns. Fail open (empty) if missing or
    malformed; a scanner that cannot load must never block a write, matching
    scan.sh's fail-open-when-Python-is-unavailable behavior."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


_GROUPS = load_patterns(_PATTERNS_PATH)


def _compiled(group: str) -> list:
    return [re.compile(p) for p in _GROUPS.get(group, {}).get("patterns", [])]


def _meta(group: str) -> tuple:
    g = _GROUPS.get(group, {})
    return (g.get("control", ""), g.get("maps_to", ""),
            g.get("what", ""), g.get("fix", ""))


# CTRL-3 secrets; CTRL-4 weak_crypto + tls_off. Compiled once at import;
# render_report.py imports these three names unchanged.
SECRET_PATTERNS = _compiled("secret")
WEAK_CRYPTO_PATTERNS = _compiled("weak_crypto")
TLS_OFF_PATTERNS = _compiled("tls_off")

_SECRET_META = _meta("secret")
_WEAK_META = _meta("weak_crypto")
_TLS_META = _meta("tls_off")


def relative_path(file_path: str, cwd: str) -> str:
    """Make the absolute, possibly-backslashed file_path relative to cwd."""
    fp = file_path.replace("\\", "/")
    cw = cwd.replace("\\", "/").rstrip("/")
    if cw and fp.lower().startswith(cw.lower() + "/"):
        return fp[len(cw) + 1:]
    return fp


def glob_to_regex(glob: str) -> str:
    """Translate a path glob to a regex. '**' matches across directory
    separators (including none); '*' matches within a single segment."""
    out, i, n = ["^"], 0, len(glob)
    while i < n:
        if glob[i:i + 2] == "**":
            i += 2
            if i < n and glob[i] == "/":
                i += 1
                out.append("(?:.*/)?")   # '**/' -> zero or more leading segments
            else:
                out.append(".*")         # trailing '**' -> anything
        elif glob[i] == "*":
            out.append("[^/]*")          # '*' -> within one segment
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    out.append("$")
    return "".join(out)


def load_scope(path: str) -> tuple[list[str], list[str]]:
    """Read scope.include / scope.exclude globs from .compliance.yml.

    A tiny line-based reader (the file is simple and ours) so the hook needs no
    YAML dependency.
    """
    include: list[str] = []
    exclude: list[str] = []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return include, exclude

    in_scope_block = False
    bucket: list[str] | None = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:                                  # a top-level key
            in_scope_block = stripped.rstrip(":") == "scope"
            bucket = None
        elif in_scope_block and stripped in ("include:", "exclude:"):
            bucket = include if stripped == "include:" else exclude
        elif in_scope_block and bucket is not None and stripped.startswith("-"):
            item = stripped[1:].strip().strip("\"'")
            if item:
                bucket.append(item)
    return include, exclude


def in_scope(rel: str, include: list[str], exclude: list[str]) -> bool:
    """In scope = matches an include glob and no exclude glob."""
    if not any(re.match(glob_to_regex(g), rel) for g in include):
        return False
    if any(re.match(glob_to_regex(g), rel) for g in exclude):
        return False
    return True


def find_violations(content: str) -> list[tuple[str, str, str, str]]:
    """Return (control, maps_to, what, fix) for each deterministic violation."""
    hits = []
    if any(p.search(content) for p in SECRET_PATTERNS):
        hits.append(_SECRET_META)
    weak = any(p.search(content) for p in WEAK_CRYPTO_PATTERNS)
    tls = any(p.search(content) for p in TLS_OFF_PATTERNS)
    if weak or tls:
        what = []
        if weak:
            what.append(_WEAK_META[2])
        if tls:
            what.append(_TLS_META[2])
        control, maps_to, _, fix = _WEAK_META
        hits.append((control, maps_to, " and ".join(what), fix))
    return hits


def build_reason(rel: str, hits: list[tuple[str, str, str, str]]) -> str:
    """The deny reason, shown verbatim to Claude and the user (the teach channel)."""
    parts = [f"Compliance Support blocked this write to {rel} (PCI-scoped):"]
    for control, maps_to, what, fix in hits:
        parts.append(f"- {control} ({maps_to}): {what}. Fix: {fix}.")
    parts.append("Fix and re-save to proceed.")
    return " ".join(parts)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed payload -> don't block

    tool_input = payload.get("tool_input") or {}
    content = tool_input.get("content") or tool_input.get("new_string") or ""
    file_path = tool_input.get("file_path") or ""
    cwd = payload.get("cwd") or ""
    if not content or not file_path:
        return

    rel = relative_path(file_path, cwd)
    include, exclude = load_scope(os.path.join(cwd, ".compliance.yml")) if cwd else ([], [])
    if not in_scope(rel, include, exclude):
        return  # out of scope -> allow (e.g. dev tooling under scripts/)

    hits = find_violations(content)
    if not hits:
        return  # clean -> allow

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": build_reason(rel, hits),
    }}))


if __name__ == "__main__":
    main()
