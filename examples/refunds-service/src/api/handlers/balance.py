"""Read-only balance endpoint.

In PCI scope but clean: it is a read (no audit-log entry required), it logs only
an internal account id (not card data or PII), and it goes through the
parameterized query layer. The ``compliance-review`` agent should NOT flag this file,
it is here to prove the gate is precise, not noisy.
"""
from __future__ import annotations

import logging

from ...db import queries
from ..auth.middleware import require_scope

log = logging.getLogger("refunds.balance")


@require_scope("refunds:read")
def get_balance(request, account_id: str):
    """Return the refundable balance for an account."""
    with request.db.cursor() as cursor:
        row = queries.get_refund(cursor, account_id)
    # Logs the internal account id only, never card data or PII.
    log.info("balance requested for account %s", account_id)
    return {"account_id": account_id, "balance": row["amount"] if row else 0}
