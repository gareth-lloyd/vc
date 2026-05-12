"""Accounts app views."""

from __future__ import annotations

from accounts.views.auth import (
    AuthSessionViewSet,
    LoginView,
    LogoutView,
    MagicLinkConsumeView,
    MagicLinkRequestView,
    MeView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PermissionsView,
    TfaChallengeView,
    TfaDisableView,
    TfaEnrollView,
    TfaVerifyView,
)
from accounts.views.contact import (
    ContactEmailViewSet,
    ContactInvitePortalView,
    ContactPhoneViewSet,
    ContactPropertiesView,
    ContactViewSet,
    SetPrimaryEmailView,
    SetPrimaryPhoneView,
)
from accounts.views.role import role_list
from accounts.views.user import (
    UserSessionRevokeView,
    UserSessionsView,
    UserViewSet,
)

__all__ = [
    "AuthSessionViewSet",
    "ContactEmailViewSet",
    "ContactInvitePortalView",
    "ContactPhoneViewSet",
    "ContactPropertiesView",
    "ContactViewSet",
    "LoginView",
    "LogoutView",
    "MagicLinkConsumeView",
    "MagicLinkRequestView",
    "MeView",
    "PasswordChangeView",
    "PasswordResetConfirmView",
    "PasswordResetRequestView",
    "PermissionsView",
    "SetPrimaryEmailView",
    "SetPrimaryPhoneView",
    "TfaChallengeView",
    "TfaDisableView",
    "TfaEnrollView",
    "TfaVerifyView",
    "UserSessionRevokeView",
    "UserSessionsView",
    "UserViewSet",
    "role_list",
]
