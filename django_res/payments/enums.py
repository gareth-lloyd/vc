"""TextChoices used across the payments app.

Kept flat for scannability; closed sets live here, not on the models.
"""

from __future__ import annotations

from django.db import models


class PaymentPurpose(models.TextChoices):
    DEPOSIT = "deposit", "Deposit"
    BALANCE = "balance", "Balance"
    SECURITY_DEPOSIT = "security_deposit", "Security deposit"
    CONCIERGE = "concierge", "Concierge"
    REFUND = "refund", "Refund"
    ADJUSTMENT = "adjustment", "Adjustment"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"
    WAIVED = "waived", "Waived"


# Statuses that count as a row "occupying" the active-per-purpose slot for the
# DEPOSIT / BALANCE invariant.
ACTIVE_PAYMENT_STATUSES: tuple[str, ...] = (
    PaymentStatus.PENDING.value,
    PaymentStatus.PROCESSING.value,
    PaymentStatus.SUCCEEDED.value,
)

# Statuses that fire `payment_succeeded` / `payment_failed` style signals.
TERMINAL_PAYMENT_STATUSES: tuple[str, ...] = (
    PaymentStatus.SUCCEEDED.value,
    PaymentStatus.FAILED.value,
    PaymentStatus.REFUNDED.value,
    PaymentStatus.CANCELLED.value,
    PaymentStatus.EXPIRED.value,
    PaymentStatus.WAIVED.value,
)


class PaymentProvider(models.TextChoices):
    FLYWIRE = "flywire", "Flywire"
    MANUAL_BANK_TRANSFER = "manual_bank_transfer", "Manual bank transfer"
    STRIPE = "stripe", "Stripe"
    OTHER = "other", "Other"


class PaymentMethod(models.TextChoices):
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    OTHER = "other", "Other"


class RefundStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXECUTING = "executing", "Executing"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


TERMINAL_REFUND_STATUSES: tuple[str, ...] = (
    RefundStatus.REJECTED.value,
    RefundStatus.CANCELLED.value,
    RefundStatus.SUCCEEDED.value,
    RefundStatus.FAILED.value,
)


class RefundReasonCode(models.TextChoices):
    CANCELLATION = "cancellation", "Cancellation"
    OVERPAYMENT = "overpayment", "Overpayment"
    GOODWILL = "goodwill", "Goodwill"
    SECURITY_DEPOSIT_RELEASE = "security_deposit_release", "Security deposit release"
    DUPLICATE_CHARGE = "duplicate_charge", "Duplicate charge"
    OTHER = "other", "Other"


class RefundMethod(models.TextChoices):
    ONLINE_GATEWAY = "online_gateway", "Online gateway"
    MANUAL_BANK_TRANSFER = "manual_bank_transfer", "Manual bank transfer"
    OFFLINE = "offline", "Offline"


class RefundPurposeTrack(models.TextChoices):
    """Which money track this refund is against. Mirrors `PaymentPurpose` minus
    `REFUND`, plus `GOODWILL`.
    """

    DEPOSIT = "deposit", "Deposit"
    BALANCE = "balance", "Balance"
    SECURITY_DEPOSIT = "security_deposit", "Security deposit"
    ADJUSTMENT = "adjustment", "Adjustment"
    GOODWILL = "goodwill", "Goodwill"


class SecurityDepositKind(models.TextChoices):
    PRE_AUTH_HOLD = "pre_auth_hold", "Pre-auth hold"
    BT_REFUNDABLE = "bt_refundable", "Bank-transfer refundable"


class SecurityDepositStatus(models.TextChoices):
    # Pre-auth path
    AWAITING_DETAILS = "awaiting_details", "Awaiting details"
    PRE_AUTHED = "pre_authed", "Pre-authed"
    RELEASED = "released", "Released"
    CAPTURED = "captured", "Captured"
    EXPIRED = "expired", "Expired"
    FAILED = "failed", "Failed"
    # BT-refundable path
    AWAITING_BT = "awaiting_bt", "Awaiting bank transfer"
    HELD = "held", "Held"
    REFUNDED = "refunded", "Refunded"
    PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"


TERMINAL_SD_STATUSES: tuple[str, ...] = (
    SecurityDepositStatus.RELEASED.value,
    SecurityDepositStatus.CAPTURED.value,
    SecurityDepositStatus.EXPIRED.value,
    SecurityDepositStatus.FAILED.value,
    SecurityDepositStatus.REFUNDED.value,
    SecurityDepositStatus.PARTIALLY_REFUNDED.value,
)


class WebhookProvider(models.TextChoices):
    FLYWIRE = "flywire", "Flywire"
    STRIPE = "stripe", "Stripe"


class EventSource(models.TextChoices):
    USER = "user", "User"
    WEBHOOK = "webhook", "Webhook"
    ADMIN = "admin", "Admin"
    SYSTEM = "system", "System"
