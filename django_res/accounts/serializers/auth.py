"""Auth-flow serializers (login, password-change, 2FA, /auth/me, sessions)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from accounts.models import User


class LoginSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer[dict[str, Any]]):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8)


class UserMeSerializer(serializers.ModelSerializer[User]):
    """Profile representation returned by /auth/me."""

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "tfa_method",
            "tfa_enrolled_at",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "tfa_method",
            "tfa_enrolled_at",
            "last_login",
        ]


class TfaEnrollSerializer(serializers.Serializer[dict[str, Any]]):
    """Posted by `POST /auth/2fa:enroll`.

    No request body required; `code` confirms the freshly-issued secret on a
    second call to `:enroll` (idempotent confirm path).
    """

    code = serializers.CharField(required=False, allow_blank=True)


class TfaChallengeSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class TfaVerifySerializer(serializers.Serializer[dict[str, Any]]):
    challenge_token = serializers.CharField()
    code = serializers.CharField()


class SessionInfoSerializer(serializers.Serializer[dict[str, Any]]):
    session_key = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_seen_at = serializers.DateTimeField()
    user_agent = serializers.CharField(allow_blank=True)
    ip = serializers.IPAddressField(allow_null=True)
