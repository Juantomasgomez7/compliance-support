"""Runtime configuration for the refunds service.

Secrets are read from the environment, never hardcoded. In production these are
injected from the platform's secrets manager. This is the clean counterpart to
the hardcoded key in ``api/handlers/refund.py``.
"""
from __future__ import annotations

import os


class Settings:
    # Processor credentials come from the environment, not from source.
    processor_api_key: str = os.environ["PROCESSOR_API_KEY"]
    processor_url: str = os.environ.get("PROCESSOR_URL", "https://processor.internal/v1")

    # Outbound calls to the processor always verify TLS.
    verify_tls: bool = True


settings = Settings()
