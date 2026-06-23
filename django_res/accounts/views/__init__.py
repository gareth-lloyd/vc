"""Accounts app views."""

from __future__ import annotations

from accounts.views.auth import (
    AuthSessionViewSet,
    CsrfView,
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
    ContactAnonymizeView,
    ContactEmailViewSet,
    ContactInvitePortalView,
    ContactMergeView,
    ContactPhoneViewSet,
    ContactPropertiesView,
    ContactRelationshipViewSet,
    ContactViewSet,
    SetPrimaryEmailView,
    SetPrimaryPhoneView,
)
from accounts.views.organisation import OrganisationMergeView, OrganisationViewSet
from accounts.views.role import role_list
from accounts.views.user import (
    UserSessionRevokeView,
    UserSessionsView,
    UserViewSet,
)

__all__ = [
    "AuthSessionViewSet",
    "ContactAnonymizeView",
    "ContactEmailViewSet",
    "ContactInvitePortalView",
    "ContactMergeView",
    "ContactPhoneViewSet",
    "ContactPropertiesView",
    "ContactRelationshipViewSet",
    "ContactViewSet",
    "CsrfView",
    "LoginView",
    "LogoutView",
    "MagicLinkConsumeView",
    "MagicLinkRequestView",
    "MeView",
    "OrganisationMergeView",
    "OrganisationViewSet",
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
