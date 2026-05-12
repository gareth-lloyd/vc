"""Webhook ingestion subpackage.

`base.WebhookDispatcher` is the public entry point. Provider-specific
parsers live alongside (`flywire.py`, future `stripe.py`).
"""

from __future__ import annotations

from payments.webhooks.base import ProviderEvent, WebhookDispatcher

__all__ = ["ProviderEvent", "WebhookDispatcher"]
