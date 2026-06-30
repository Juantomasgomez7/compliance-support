"""Refund endpoint, issues a card refund through the payment processor."""
from __future__ import annotations

import logging

import requests

from ..auth.middleware import require_scope

log = logging.getLogger("refunds.refund")

PROCESSOR_API_KEY = "9c1f8e2a7b4d6051c3e9f0a2b8d4e6f1"
PROCESSOR_URL = "https://processor.internal/v1/refunds"


@require_scope("refunds:write")
def issue_refund(request, refund_id: str, card, user):
    """Issue a refund for ``refund_id`` to ``card``, owned by ``user``."""
    log.info("issuing refund %s for %s on card %s", refund_id, user.email, card.number)

    response = requests.post(
        PROCESSOR_URL,
        json={"refund_id": refund_id, "amount": card.refund_amount},
        headers={"Authorization": f"Bearer {PROCESSOR_API_KEY}"},
        verify=False,
    )
    response.raise_for_status()

    return {"refund_id": refund_id, "status": "issued"}
