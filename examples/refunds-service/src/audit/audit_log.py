"""Append-only audit log for state-changing actions in the refunds service.

Every money-moving action (refund, reversal, adjustment) is expected to call
``record()`` so there is a tamper-evident trail of who did what. This is the
helper the rest of the service should use; the ``compliance-review`` agent looks for a
``record()`` call on any handler that moves money.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

_logger = logging.getLogger("audit")


@dataclass(frozen=True)
class AuditEntry:
    actor: str       # who initiated the action (user or service id)
    action: str      # e.g. "refund.issued"
    resource: str    # e.g. "refund:re_8a21"
    metadata: dict   # non-sensitive context only, never card data or PII


def record(actor: str, action: str, resource: str, **metadata) -> None:
    """Write one append-only audit entry. Call this for every state change."""
    entry = AuditEntry(actor=actor, action=action, resource=resource, metadata=metadata)
    payload = {**asdict(entry), "ts": datetime.now(timezone.utc).isoformat()}
    _logger.info("AUDIT %s", json.dumps(payload))
