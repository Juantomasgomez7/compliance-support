"""Token hashing helpers.

Shows the approved primitive (bcrypt, with a per-token salt) next to a legacy
MD5 fingerprint that must NOT be used to protect secrets. The hook blocks any
*new* write that introduces weak crypto like MD5 into an in-scope path.
"""
from __future__ import annotations

import hashlib

import bcrypt


def hash_token(token: str) -> bytes:
    """Approved: bcrypt with a per-token salt for anything secret."""
    return bcrypt.hashpw(token.encode(), bcrypt.gensalt())


def legacy_fingerprint(token: str) -> str:
    """Legacy MD5 fingerprint, weak; do not use this for secrets."""
    return hashlib.md5(token.encode()).hexdigest()
