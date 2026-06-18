"""URL routing for the accounts app.

Covers /auth/*, /users, /contacts, /roles per §2.1 / §2.15 / §2.18 of the
REST API surface spec.
"""

from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from accounts import views

router = DefaultRouter(trailing_slash=False)
router.register(r"users", views.UserViewSet, basename="user")
router.register(r"contacts", views.ContactViewSet, basename="contact")


# Manual paths for colon-verb actions and nested sub-resources. DRF's routers
# can't emit `:action` URLs because they hard-code trailing-slash globbing.

auth_patterns = [
    path("auth/csrf", views.CsrfView.as_view(), name="auth-csrf"),
    path("auth/login", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me", views.MeView.as_view(), name="auth-me"),
    path("auth/me/password", views.PasswordChangeView.as_view(), name="auth-me-password"),
    path("auth/permissions", views.PermissionsView.as_view(), name="auth-permissions"),
    path(
        "auth/sessions",
        views.AuthSessionViewSet.as_view({"get": "list"}),
        name="auth-sessions",
    ),
    path(
        "auth/sessions/<int:pk>",
        views.AuthSessionViewSet.as_view({"delete": "destroy"}),
        name="auth-session-detail",
    ),
    path("auth/2fa:challenge", views.TfaChallengeView.as_view(), name="auth-2fa-challenge"),
    path("auth/2fa:verify", views.TfaVerifyView.as_view(), name="auth-2fa-verify"),
    path("auth/2fa:enroll", views.TfaEnrollView.as_view(), name="auth-2fa-enroll"),
    path("auth/2fa:disable", views.TfaDisableView.as_view(), name="auth-2fa-disable"),
    path(
        "auth/password-reset:request",
        views.PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "auth/password-reset:confirm",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path(
        "auth/magic-link:request",
        views.MagicLinkRequestView.as_view(),
        name="auth-magic-link-request",
    ),
    path(
        "auth/magic-link:consume",
        views.MagicLinkConsumeView.as_view(),
        name="auth-magic-link-consume",
    ),
]

user_action_patterns = [
    path(
        "users/<int:pk>:activate",
        views.UserViewSet.as_view({"post": "activate"}),
        name="user-activate",
    ),
    path(
        "users/<int:pk>:reset-password",
        views.UserViewSet.as_view({"post": "reset_password"}),
        name="user-reset-password",
    ),
    path(
        "users/<int:pk>:reset-2fa",
        views.UserViewSet.as_view({"post": "reset_tfa"}),
        name="user-reset-2fa",
    ),
    path(
        "users/<int:user_pk>/sessions",
        views.UserSessionsView.as_view({"get": "list"}),
        name="user-sessions",
    ),
    path(
        "users/<int:user_pk>/sessions/<int:pk>",
        views.UserSessionRevokeView.as_view({"delete": "destroy"}),
        name="user-session-revoke",
    ),
]

contact_nested_patterns = [
    path(
        "contacts/<int:contact_pk>/emails",
        views.ContactEmailViewSet.as_view({"get": "list", "post": "create"}),
        name="contact-emails",
    ),
    path(
        "contacts/<int:contact_pk>/emails/<int:pk>",
        views.ContactEmailViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="contact-email-detail",
    ),
    path(
        "contacts/<int:contact_pk>/emails/<int:email_pk>:set-primary",
        views.SetPrimaryEmailView.as_view({"post": "create"}),
        name="contact-email-set-primary",
    ),
    path(
        "contacts/<int:contact_pk>/phones",
        views.ContactPhoneViewSet.as_view({"get": "list", "post": "create"}),
        name="contact-phones",
    ),
    path(
        "contacts/<int:contact_pk>/phones/<int:pk>",
        views.ContactPhoneViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="contact-phone-detail",
    ),
    path(
        "contacts/<int:contact_pk>/phones/<int:phone_pk>:set-primary",
        views.SetPrimaryPhoneView.as_view({"post": "create"}),
        name="contact-phone-set-primary",
    ),
    path(
        "contacts/<int:contact_pk>:invite-portal",
        views.ContactInvitePortalView.as_view({"post": "create"}),
        name="contact-invite-portal",
    ),
    path(
        "contacts/<int:contact_pk>:merge",
        views.ContactMergeView.as_view({"post": "create"}),
        name="contact-merge",
    ),
    path(
        "contacts/<int:contact_pk>:anonymize",
        views.ContactAnonymizeView.as_view({"post": "create"}),
        name="contact-anonymize",
    ),
]

role_patterns = [
    path("roles", views.role_list, name="role-list"),
]

urlpatterns = [
    # Action / nested patterns MUST precede the router's CRUD routes: DRF's
    # `/<pk>` pattern is `[^/.]+`, which would otherwise greedily match
    # `1:invite-portal` as `pk=1:invite-portal`.
    *auth_patterns,
    *user_action_patterns,
    *contact_nested_patterns,
    *role_patterns,
    *router.urls,
]
