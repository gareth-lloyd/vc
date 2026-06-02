"""Serializers for /users (admin staff CRUD)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from accounts.models import User
from core.enums import StaffRole


class UserSerializer(serializers.ModelSerializer[User]):
    """Detail/list representation of a staff user."""

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
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "tfa_method",
            "tfa_enrolled_at",
            "last_login",
            "date_joined",
        ]


class UserCreateSerializer(serializers.ModelSerializer[User]):
    """Admin create body — accepts a password and a role."""

    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    role = serializers.ChoiceField(choices=StaffRole.choices, default=StaffRole.VIEWER)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "is_staff",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data: dict[str, Any]) -> User:
        password = validated_data.pop("password")
        is_staff = validated_data.pop("is_staff", False)
        user: User = User.objects.create_user(
            email=validated_data.pop("email"),
            password=password,
            is_staff=is_staff,
            **validated_data,
        )
        return user
