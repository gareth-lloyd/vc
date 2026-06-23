"""Accounts app serializers."""

from __future__ import annotations

from accounts.serializers.auth import (
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    SessionInfoSerializer,
    TfaChallengeSerializer,
    TfaEnrollSerializer,
    TfaVerifySerializer,
    UserMeSerializer,
)
from accounts.serializers.contact import (
    ContactEmailSerializer,
    ContactMergeSerializer,
    ContactPhoneSerializer,
    ContactSerializer,
)
from accounts.serializers.organisation import (
    OrganisationMergeSerializer,
    OrganisationSerializer,
    OrganisationSummarySerializer,
)
from accounts.serializers.person_relationship import LinkedContactSerializer
from accounts.serializers.user import UserCreateSerializer, UserSerializer

__all__ = [
    "ContactEmailSerializer",
    "ContactMergeSerializer",
    "ContactPhoneSerializer",
    "ContactSerializer",
    "LinkedContactSerializer",
    "LoginSerializer",
    "OrganisationMergeSerializer",
    "OrganisationSerializer",
    "OrganisationSummarySerializer",
    "PasswordChangeSerializer",
    "PasswordResetRequestSerializer",
    "SessionInfoSerializer",
    "TfaChallengeSerializer",
    "TfaEnrollSerializer",
    "TfaVerifySerializer",
    "UserCreateSerializer",
    "UserMeSerializer",
    "UserSerializer",
]
