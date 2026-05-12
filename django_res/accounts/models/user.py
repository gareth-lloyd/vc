from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.enums import StaffRole, TfaMethod
from accounts.managers import UserManager
from core.fields import EncryptedTextField


class User(AbstractUser):
    """Email-authenticated staff user with 2FA fields and a coarse role enum."""

    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, blank=True)

    tfa_method = models.CharField(
        max_length=8,
        choices=TfaMethod.choices,
        default=TfaMethod.NONE,
    )
    tfa_secret = EncryptedTextField(blank=True, default="")
    tfa_enrolled_at = models.DateTimeField(null=True, blank=True)
    # Hashed (pbkdf2) single-use recovery codes; plaintext shown once at enroll.
    tfa_recovery_codes = models.JSONField(default=list, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    role = models.CharField(
        max_length=16,
        choices=StaffRole.choices,
        default=StaffRole.VIEWER,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()  # type: ignore[assignment,misc]

    class Meta(AbstractUser.Meta):
        swappable = "AUTH_USER_MODEL"

    def __str__(self) -> str:
        return self.email
