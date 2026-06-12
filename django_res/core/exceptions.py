"""Typed domain exceptions used across services.

These are not HTTP exceptions; views/handlers translate them into appropriate
DRF responses (usually 400 / 409 / 422). The exceptions exist to make the
business-logic call surface explicit.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for typed domain errors.

    The HTTP `status_code` defaults to 409 (Conflict) — the canonical "state
    refused this operation" code. Subclasses that represent malformed input
    rather than a state mismatch should override it to 400.
    """

    code: str = "domain_error"
    status_code: int = 409


class InvalidTransition(DomainError):
    """A state machine transition was attempted from a disallowed source."""

    code = "invalid_transition"

    def __init__(self, from_state: str, to_state: str, *, allowed: list[str] | None = None) -> None:
        super().__init__(f"Cannot transition from {from_state!r} to {to_state!r}")
        self.from_state = from_state
        self.to_state = to_state
        self.allowed = allowed or []


class NoRateAvailable(DomainError):
    code = "no_rate_available"


class PartyOutOfRange(DomainError):
    code = "party_out_of_range"


class DiscountNotApplicable(DomainError):
    code = "discount_not_applicable"


class MinNightsNotMet(DomainError):
    code = "min_nights_not_met"


class HoldUnavailable(DomainError):
    code = "hold_unavailable"


class ReadOnlyHold(DomainError):
    """A system-managed hold (quotation / booking) cannot be hand-edited.

    These are released via their originating quotation/booking, not the
    availability-block endpoints.
    """

    code = "read_only_hold"


class QuotationLocked(DomainError):
    """The quotation is past the point where it can be edited or deleted.

    ACCEPTED/EXPIRED/CANCELLED quotations are closed records — the terms the
    guest accepted (or the dead quote's audit shape) must not drift after the
    fact. DRAFT and SENT remain editable (pre-acceptance renegotiation).
    """

    code = "quotation_locked"


class OverlappingBooking(DomainError):
    code = "overlapping_booking"

    def __init__(self, message: str = "", *, booking: object | None = None) -> None:
        """Optionally carry the booking that occupies the range.

        Stored untyped (``object``) so `core` keeps importing no domain app —
        callers in `reservations` narrow it back to a `Booking`.
        """
        super().__init__(message)
        self.booking = booking


class TerminalBookingExists(DomainError):
    """The quotation line already produced a booking that has since closed.

    Converting again must not resurface a CANCELLED/EXPIRED/DECLINED booking
    as a fresh success — re-booking goes through a new quotation.
    """

    code = "terminal_booking_exists"


class TermsNotAccepted(DomainError):
    """A booking-creating request arrived without the explicit acceptance flag.

    `Booking.terms_accepted_at` is stamped server-side; the API must receive
    `terms_accepted: true` as the acceptance signal (SMELL-006).
    """

    code = "terms_not_accepted"
    status_code = 400


class OAuthNotConnectedError(DomainError):
    code = "oauth_not_connected"


class NoPendingPayment(DomainError):
    code = "no_pending_payment"


class InvalidPaymentState(DomainError):
    code = "invalid_state"


class NoActiveSecurityDeposit(DomainError):
    code = "no_active_sd"


class InvalidSecurityDepositKind(DomainError):
    """An SD action was invoked against the wrong `SecurityDepositKind`.

    Distinct from `InvalidPaymentState`: the *kind* (pre-auth hold vs.
    BT-refundable), not the status, is what refuses the operation —
    `:hold` only applies to PRE_AUTH_HOLD, `:mark-paid` only to
    BT_REFUNDABLE (BUG-011).
    """

    code = "invalid_sd_kind"


class UnknownAction(DomainError):
    code = "unknown_action"
    status_code = 400
