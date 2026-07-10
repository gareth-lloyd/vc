"""Seed staff users (one Person + email/phone per user).

Also ensures two well-known superusers exist on every run so a developer can
log in without hunting through generated rows. These are upserted by email
(password is reset each run) and are independent of the per-run batch. The
primary superuser (glloyd@gmail.com) is also pre-enrolled in TOTP 2FA with a
fixed secret so a DB drop + reseed keeps the same authenticator codes — see
`_DEV_TFA_SECRET`.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from accounts.enums import TfaMethod
from accounts.factories import PersonEmailFactory, PersonPhoneFactory, UserFactory
from accounts.models import User
from core.enums import StaffRole
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Fixed TOTP secret for the primary dev superuser. 2FA state lives as encrypted
# columns on accounts_user (no device table), so a dropped-and-reseeded DB would
# strip any enrolled secret and force re-enrolment every time. Seeding this fixed
# secret makes every reseed reproduce the same authenticator codes — it is the
# secret already enrolled in the dev DB, so the existing app entry keeps working.
# Dev-only, a known throwaway credential like the hardcoded passwords below —
# only applied where 2FA is NOT enforced (see _ensure_superuser), so it never
# weakens the real 2FA gate on staging/production.
_DEV_TFA_SECRET = "HORSTX4N5AA4IKSUR3USHIMQJMLU6OUO"  # 32-char base32

# (email, password, first_name, last_name, tfa_secret) for the always-on dev
# superusers. Only glloyd is pre-enrolled in 2FA; None leaves the account
# password-only (tfa_method stays NONE).
_SUPERUSERS: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("glloyd@gmail.com", "fiery-kite-pumpkin-eton", "Gareth", "Lloyd", _DEV_TFA_SECRET),
    ("nick@villacollective.com", "purple-octagon-ferry-palace", "Nick", "Villa", None),
    ("ben@mojomedia.co.uk", "cobalt-heron-marble-quay", "Ben", "Mojo", None),
)


def _ensure_dev_2fa(user: User, secret: str) -> None:
    """Pre-enrol `user` in TOTP with the fixed `secret` (idempotent).

    Mirrors what TwoFactorService.enroll + confirm_enrollment persist, minus
    recovery codes (tfa_recovery_codes defaults to [] — verify() over an empty
    list is a no-op). Skips when already enrolled with this exact secret so an
    additive re-seed against a live DB doesn't reset the single-use replay guard
    (tfa_last_verified_step); tfa_secret decrypts on read, so the compare works.
    """
    if user.tfa_method == TfaMethod.TOTP and user.tfa_secret == secret:
        return
    user.tfa_method = TfaMethod.TOTP
    user.tfa_secret = secret  # EncryptedTextField encrypts on save
    user.tfa_enrolled_at = user.tfa_enrolled_at or timezone.now()
    user.save(update_fields=["tfa_method", "tfa_secret", "tfa_enrolled_at"])


def _ensure_superuser(
    email: str, password: str, first_name: str, last_name: str, tfa_secret: str | None
) -> int:
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "is_staff": True,
            "is_superuser": True,
            "role": StaffRole.ADMIN,
        },
    )
    user.first_name = first_name
    user.last_name = last_name
    user.is_staff = True
    user.is_superuser = True
    user.role = StaffRole.ADMIN
    user.set_password(password)
    user.save()
    # Only pre-seed the repo-committed 2FA secret where 2FA is NOT enforced
    # (dev/test). On staging/production (TFA_ENFORCED) a real second factor
    # matters, so never inject a public secret — let the user enrol their own.
    if tfa_secret is not None and not settings.TFA_ENFORCED:
        _ensure_dev_2fa(user, tfa_secret)
    return int(created)


def _run(ctx: SeedContext) -> int:
    made = 0
    for email, password, first_name, last_name, tfa_secret in _SUPERUSERS:
        made += _ensure_superuser(email, password, first_name, last_name, tfa_secret)

    for _ in range(ctx.n_users):
        contact = PersonEmailFactory().contact
        PersonPhoneFactory(contact=contact)
        UserFactory()
        made += 1
    return made


register(Stage(name="users", run=_run))
