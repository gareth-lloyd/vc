"""`SyncClient` ABC — interface every provider client implements.

Concrete subclasses (see `integrations.services.zoho.ZohoSyncClient`) own
the wire-level concerns (auth, request shape). The orchestration tasks in
`integrations.tasks` work against this interface so adding a new provider
is a single new subclass.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.db.models import Model

    from integrations.models import SyncIssue, SyncRecord


class SyncClient(ABC):
    """Stateless per-provider sync interface."""

    provider: str

    @abstractmethod
    def push(self, instance: Model) -> SyncRecord:
        """Push the local row to the provider and return the updated SyncRecord."""
        raise NotImplementedError

    @abstractmethod
    def pull(self, external_id: str) -> dict[str, Any]:
        """Fetch the remote row by external id and return the raw payload."""
        raise NotImplementedError

    @abstractmethod
    def reconcile(self, instance: Model) -> SyncIssue | None:
        """Compare local + remote; return a SyncIssue when they disagree."""
        raise NotImplementedError

    @abstractmethod
    def fingerprint(self, payload: dict[str, Any]) -> str:
        """Stable hash of the sync-covered fields, used for drift detection."""
        raise NotImplementedError
