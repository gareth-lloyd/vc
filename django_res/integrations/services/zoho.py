"""ZohoSyncClient skeleton.

The Zoho integration is wired in v1.1 — for now the wire calls raise
NotImplementedError. The OAuth flow that backs this client
(`integrations.services.oauth.OAuthService`) is the real implementation
landing first; this client picks up tokens from there via
`OAuthService.get_access_token("ZOHO_CRM")` once the push/pull logic is
fleshed out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from integrations.enums import SyncProvider
from integrations.services.sync_client import SyncClient

if TYPE_CHECKING:
    from django.db.models import Model

    from integrations.models import SyncIssue, SyncRecord


class ZohoSyncClient(SyncClient):
    """Pushes Property/Quotation/Booking/Guest to Zoho CRM (wired in v1.1)."""

    provider: str = SyncProvider.ZOHO_CRM.value

    def push(self, instance: Model) -> SyncRecord:
        """Push the instance to Zoho CRM. Wired in v1.1."""
        raise NotImplementedError("ZohoSyncClient.push is wired in v1.1")

    def pull(self, external_id: str) -> dict[str, Any]:
        """Pull the Zoho CRM record for `external_id`. Wired in v1.1."""
        raise NotImplementedError("ZohoSyncClient.pull is wired in v1.1")

    def reconcile(self, instance: Model) -> SyncIssue | None:
        """Reconcile the local row against Zoho CRM. Wired in v1.1."""
        raise NotImplementedError("ZohoSyncClient.reconcile is wired in v1.1")

    def fingerprint(self, payload: dict[str, Any]) -> str:
        """Stable hash of Zoho-covered fields. Wired in v1.1."""
        raise NotImplementedError("ZohoSyncClient.fingerprint is wired in v1.1")
