from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import User
from integrations.enums import OAuthProvider
from integrations.models import OAuthCredential
from integrations.services.oauth import (
    OAuthService,
    OAuthStateError,
    TokenPayload,
)


@pytest.fixture
def actor(db: None) -> User:
    return User.objects.create_user(email="ops@example.com", password="secret")


def _stub_exchange(provider: str, code: str) -> TokenPayload:
    return TokenPayload(
        access_token=f"access-{provider}-{code}",
        refresh_token=f"refresh-{provider}-{code}",
        expires_in=3600,
        scope="ZohoCRM.modules.ALL",
        account_id="acct-1",
        meta={"api_domain": "https://www.zohoapis.com"},
    )


@pytest.mark.django_db
def test_begin_returns_signed_state(actor: User) -> None:
    service = OAuthService()

    state = service.begin(OAuthProvider.ZOHO_CRM.value, actor=actor)

    assert isinstance(state, str)
    # Signed values contain the original payload and signature delimiters.
    assert state.count(":") >= 2
    assert state.startswith(f"{OAuthProvider.ZOHO_CRM.value}:{actor.pk}")


@pytest.mark.django_db
def test_complete_validates_state_and_writes_credential(actor: User) -> None:
    service = OAuthService()
    state = service.begin(OAuthProvider.ZOHO_CRM.value, actor=actor)

    credential = service.complete(
        OAuthProvider.ZOHO_CRM.value,
        code="auth-code-abc",
        state=state,
        actor=actor,
        token_exchange=_stub_exchange,
    )

    assert credential.is_active
    assert credential.access_token == "access-ZOHO_CRM-auth-code-abc"
    assert credential.refresh_token == "refresh-ZOHO_CRM-auth-code-abc"
    assert credential.connected_by_id == actor.pk
    assert credential.expires_at > timezone.now()


@pytest.mark.django_db
def test_complete_with_mismatched_state_raises(actor: User) -> None:
    service = OAuthService()

    with pytest.raises(OAuthStateError):
        service.complete(
            OAuthProvider.ZOHO_CRM.value,
            code="auth-code-abc",
            state="not-a-valid-state",
            actor=actor,
            token_exchange=_stub_exchange,
        )


@pytest.mark.django_db
def test_complete_with_state_for_different_actor_raises(actor: User) -> None:
    other = User.objects.create_user(email="other@example.com", password="secret")
    service = OAuthService()
    state_for_other = service.begin(OAuthProvider.ZOHO_CRM.value, actor=other)

    with pytest.raises(OAuthStateError):
        service.complete(
            OAuthProvider.ZOHO_CRM.value,
            code="auth-code-abc",
            state=state_for_other,
            actor=actor,
            token_exchange=_stub_exchange,
        )


@pytest.mark.django_db
def test_complete_deactivates_prior_active_credential(actor: User) -> None:
    service = OAuthService()
    prior = OAuthCredential.objects.create(
        provider=OAuthProvider.ZOHO_CRM,
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        is_active=True,
    )

    state = service.begin(OAuthProvider.ZOHO_CRM.value, actor=actor)
    new_credential = service.complete(
        OAuthProvider.ZOHO_CRM.value,
        code="auth-code-abc",
        state=state,
        actor=actor,
        token_exchange=_stub_exchange,
    )

    prior.refresh_from_db()
    assert prior.is_active is False
    assert prior.disconnected_at is not None
    assert new_credential.is_active is True
    assert (
        OAuthCredential.objects.filter(provider=OAuthProvider.ZOHO_CRM, is_active=True).count() == 1
    )


@pytest.mark.django_db
def test_disconnect_deactivates_active_credential(actor: User) -> None:
    service = OAuthService()
    credential = OAuthCredential.objects.create(
        provider=OAuthProvider.ZOHO_CRM,
        access_token="access",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        is_active=True,
    )

    service.disconnect(OAuthProvider.ZOHO_CRM.value, actor=actor)

    credential.refresh_from_db()
    assert credential.is_active is False
    assert credential.disconnected_at is not None


@pytest.mark.django_db
def test_disconnect_is_noop_when_no_active_credential(actor: User) -> None:
    service = OAuthService()
    # No credential exists; disconnect should silently succeed.
    service.disconnect(OAuthProvider.ZOHO_CRM.value, actor=actor)


@pytest.mark.django_db
def test_get_access_token_returns_plaintext_when_not_near_expiry() -> None:
    OAuthCredential.objects.create(
        provider=OAuthProvider.ZOHO_CRM,
        access_token="fresh-access",
        refresh_token="refresh",
        expires_at=timezone.now() + timedelta(hours=1),
        is_active=True,
    )

    token = OAuthService().get_access_token(OAuthProvider.ZOHO_CRM.value)

    assert token == "fresh-access"
