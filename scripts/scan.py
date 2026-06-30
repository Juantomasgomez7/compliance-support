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

# --- CTRL-3 - hardcoded secrets -----------------------------------------------
SECRET_PATTERNS = [
    # Provider-format keys (Stripe, AWS, GitHub, Slack, ...).
    re.compile(r"\b(?:sk_live_|rk_live_|AKIA|ghp_|gho_|xox[baprs]-)[A-Za-z0-9_\-]{8,}"),
    # A high-entropy literal assigned to a secret-ish name. The required opening
    # quote right after '=' is what lets os.environ["KEY"] through cleanly.
    re.compile(
        r"(?i)\w*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)S?\s*[:=]\s*"
        r"[\"'][A-Za-z0-9/+_\-]{16,}[\"']"
    ),
]

# --- CTRL-4 - weak crypto / disabled TLS --------------------------------------
WEAK_CRYPTO_PATTERNS = [
    re.compile(r"(?i)\b(?:md5|sha1)\s*\("),        # weak hash used as a function
    re.compile(r"(?i)hashlib\.(?:md5|sha1)\b"),
    re.compile(r"(?i)\bMODE_ECB\b|\bDES\.new\b|\bRC4\b"),
]
TLS_OFF_PATTERNS = [
    re.compile(r"(?i)verify\s*=\s*False"),
    re.compile(r"(?i)ssl\._create_unverified_context"),
]


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
        hits.append((
            "CTRL-3", "PCI Req 8",
            "a hardcoded secret / credential",
            "read it from the environment, e.g. os.environ['PROCESSOR_API_KEY']",
        ))
    weak = any(p.search(content) for p in WEAK_CRYPTO_PATTERNS)
    tls = any(p.search(content) for p in TLS_OFF_PATTERNS)
    if weak or tls:
        what = []
        if weak:
            what.append("weak/broken cryptography (e.g. MD5/DES/ECB)")
        if tls:
            what.append("disabled TLS verification (verify=False)")
        hits.append((
            "CTRL-4", "PCI Req 3 & 4 / SOC 2 CC6.7",
            " and ".join(what),
            "use a strong primitive (bcrypt / AES-GCM) and keep TLS verification on",
        ))
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
        return  # out of scope -> allow (this is the dev_seed.py precision beat)

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
