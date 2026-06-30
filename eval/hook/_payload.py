"""Emit a PreToolUse(Write) payload for the hook golden tests.

Usage: python _payload.py <repo_root> <relpath> <content>
Mirrors the real hook payload: absolute file_path + cwd (forward slashes work on
both macOS and Windows Python).
"""
import json
import sys

root, rel, content = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({
    "cwd": root,
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "tool_input": {"file_path": f"{root}/{rel}", "content": content},
}))
