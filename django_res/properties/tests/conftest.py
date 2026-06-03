"""Shared properties-test fixtures for API tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from properties.models import (
    Country,
    Property,
    PropertyCategory,
    PropertyGroup,
    Region,
)

if TYPE_CHECKING:
    pass


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def admin(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="admin@example.com",
        password="x",
        role=StaffRole.ADMIN,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def category(db: None) -> PropertyCategory:
    return PropertyCategory.objects.create(name="Villa", slug="villa")


@pytest.fixture
def group(db: None) -> PropertyGroup:
    return PropertyGroup.objects.create(name="Group A")


@pytest.fixture
def country(db: None) -> Country:
    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    return country


@pytest.fixture
def region(country: Country) -> Region:
    return Region.objects.create(country=country, name="Cornwall", slug="cornwall")


@pytest.fixture
def property_(
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> Property:
    return Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        category=category,
        group=group,
        region=region,
    )
