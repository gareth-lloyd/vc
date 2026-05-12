"""Signal receivers for transactional email dispatch.

The receivers are intentionally defined but not yet connected: the source
signals (``booking_transitioned``, ``payment_succeeded`` etc.) live in apps
that are not yet built. ``CommsConfig.ready()`` calls ``_register`` which is
currently a no-op; once the source apps exist their signal objects can be
imported here and connected without touching the wiring elsewhere.
"""

from __future__ import annotations

from typing import Any


# TODO: connect to reservations.signals.booking_transitioned once the
# reservations app emits it.
def booking_transitioned_handler(
    sender: Any,
    *,
    from_status: str,
    to_status: str,
    booking: Any,
    actor: Any | None = None,
    source: str | None = None,
    **_: Any,
) -> None:
    """Dispatch booking lifecycle emails (confirmation, declined, cancelled)."""


# TODO: connect to reservations.signals.owner_approval_requested once the
# reservations app emits it.
def owner_approval_requested_handler(
    sender: Any,
    *,
    booking: Any,
    **_: Any,
) -> None:
    """Send the owner-approval request email with a signed action link."""


# TODO: connect to reservations.signals.quotation_sent once the reservations
# app emits it.
def quotation_sent_handler(
    sender: Any,
    *,
    quotation: Any,
    sender_user: Any | None = None,
    **_: Any,
) -> None:
    """Send a quotation email as the agent (``sender_user``) when active."""


# TODO: connect to payments.signals.payment_succeeded once the payments app
# emits it.
def payment_succeeded_handler(
    sender: Any,
    *,
    payment: Any,
    **_: Any,
) -> None:
    """Send the guest receipt for a successful payment."""


# TODO: connect to payments.signals.payment_failed once the payments app
# emits it.
def payment_failed_handler(
    sender: Any,
    *,
    payment: Any,
    **_: Any,
) -> None:
    """Notify ops and guest on a failed payment."""


# TODO: connect to reservations.signals.hold_expired once the reservations
# app emits it (fired by the ``expire_stale_holds`` Celery task).
def hold_expired_handler(
    sender: Any,
    *,
    hold: Any,
    **_: Any,
) -> None:
    """Notify the agent who created the hold that it has expired."""


# TODO: connect to payments.signals.security_deposit_released once the
# payments app emits it.
def security_deposit_released_handler(
    sender: Any,
    *,
    sd: Any,
    **_: Any,
) -> None:
    """Inform the guest that their security deposit has been released."""


def _register() -> None:
    """Register signal handlers when their source signals exist.

    The current call is a no-op because no source app is built; calling it
    must remain safe so ``CommsConfig.ready()`` succeeds at import time.
    """
