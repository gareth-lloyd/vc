from __future__ import annotations

import pytest
from django.contrib import admin
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import User

# The default test settings use ManifestStaticFilesStorage, which 500s any
# admin page render without a collectstatic manifest. Swap in plain storage so
# these smoke tests exercise the admin views, not staticfiles.
plain_static = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)


@pytest.fixture
def superuser(db: None) -> User:
    return User.objects.create_superuser(email="admin@example.com", password="pw-12345-xyz")


@pytest.mark.django_db
def test_user_registered() -> None:
    assert User in admin.site._registry


@plain_static
@pytest.mark.django_db
def test_admin_changelist_renders(client: Client, superuser: User) -> None:
    client.force_login(superuser)
    resp = client.get(reverse("admin:accounts_user_changelist"))
    assert resp.status_code == 200


@plain_static
@pytest.mark.django_db
def test_admin_add_renders(client: Client, superuser: User) -> None:
    client.force_login(superuser)
    resp = client.get(reverse("admin:accounts_user_add"))
    assert resp.status_code == 200


@plain_static
@pytest.mark.django_db
def test_admin_change_renders(client: Client, superuser: User) -> None:
    target = User.objects.create_user(email="staff@example.com", password="pw-12345-xyz")
    client.force_login(superuser)
    resp = client.get(reverse("admin:accounts_user_change", args=[target.pk]))
    assert resp.status_code == 200


@plain_static
@pytest.mark.django_db
def test_admin_change_save(client: Client, superuser: User) -> None:
    target = User.objects.create_user(email="staff@example.com", password="pw-12345-xyz")
    client.force_login(superuser)
    url = reverse("admin:accounts_user_change", args=[target.pk])
    resp = client.post(
        url,
        {
            "email": "staff@example.com",
            "first_name": "New",
            "last_name": "Name",
            "phone": "",
            "preferred_language": "en",
            "role": target.role,
            "tfa_method": target.tfa_method,
            "last_login_0": "",
            "last_login_1": "",
            "date_joined_0": "2024-01-01",
            "date_joined_1": "00:00:00",
            "initial-date_joined_0": "2024-01-01",
            "initial-date_joined_1": "00:00:00",
        },
        follow=True,
    )
    target.refresh_from_db()
    assert resp.status_code == 200
    assert target.first_name == "New", f"save failed; redirect_chain={resp.redirect_chain}"
