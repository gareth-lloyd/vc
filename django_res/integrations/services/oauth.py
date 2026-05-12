"""OAuthService — orchestrates the OAuth connect/disconnect flow.

Backs the `/zoho:connect` / `/zoho:disconnect` API endpoints. State CSRF
protection uses a `django.core.signing.TimestampSigner` keyed by user +
provider (5-minute TTL). Token storage is `OAuthCredential` with
EncryptedTextField-backed access/refresh tokens.

On Postgres, the inline refresh path is wrapped in a transaction-scoped
advisory lock keyed on the credential id so two concurrent callers cannot
both refresh the same row. On SQLite (test environment) the lock is a
no-op — concurrent refreshes aren't a realistic concern there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import connection, transaction
from django.utils import timezone

from integrations.models import OAuthCredential

if TYPE_CHECKING:
    from accounts.models import User


STATE_SIGNER_SALT = "integrations.oauth.state"
STATE_MAX_AGE_SECONDS = 5 * 60
REFRESH_WINDOW = timedelta(minutes=5)


class OAuthError(Exception):
    """Base for OAuthService errors."""


class OAuthStateError(OAuthError):
    """Raised when the `state` parameter is invalid, expired, or mismatched."""


class OAuthNotConnectedError(OAuthError):
    """Raised when no active credential exists for the requested provider."""


@dataclass(frozen=True)
class TokenPayload:
    """Normalised provider token response."""

    access_token: str
    refresh_token: str
    expires_in: int  # seconds from now
    token_type: str = "Bearer"
    scope: str = ""
    account_id: str = ""
    meta: dict[str, Any] | None = None


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=STATE_SIGNER_SALT)


def _state_payload(provider: str, user_id: int) -> str:
    return f"{provider}:{user_id}"


class OAuthService:
    """OAuth-flow orchestration for provider-agnostic credential storage."""

    def begin(self, provider: str, *, actor: User) -> str:
        """Return a signed CSRF state token for the auth-code redirect.

        The state encodes `(provider, actor.id)` and is signed with a
        `TimestampSigner`. The view layer is responsible for assembling the
        provider authorization-code URL and embedding the returned token in
        the `state` query parameter.
        """
        if actor.pk is None:
            raise OAuthError("Actor must be saved before beginning OAuth flow.")
        return _signer().sign(_state_payload(provider, actor.pk))

    def complete(
        self,
        provider: str,
        code: str,
        state: str,
        *,
        actor: User,
        token_exchange: Any = None,
    ) -> OAuthCredential:
        """Validate `state`, exchange `code` for tokens, persist them.

        `token_exchange` is an injectable callable `(provider, code) -> TokenPayload`
        so the test suite (and the future real-provider wiring) can swap in a
        stub without monkey-patching. The default raises NotImplementedError;
        provider-specific exchanges are wired in alongside the live OAuth
        integration.
        """
        if actor.pk is None:
            raise OAuthError("Actor must be saved before completing OAuth flow.")
        self._validate_state(provider, state, actor)

        exchange = token_exchange or _default_token_exchange
        payload = exchange(provider, code)

        return self._persist_new_credential(provider, payload, actor)

    def disconnect(self, provider: str, *, actor: User) -> None:
        """Deactivate the active credential for `provider`.

        Best-effort: token-revocation against the provider's revoke endpoint
        is handled separately (a Celery task) so a network failure here
        doesn't strand the operator. Sets `is_active=False` and
        `disconnected_at=now()`.
        """
        try:
            credential = OAuthCredential.objects.get(provider=provider, is_active=True)
        except OAuthCredential.DoesNotExist:
            return
        credential.is_active = False
        credential.disconnected_at = timezone.now()
        credential.updated_by = actor
        credential.save(update_fields=["is_active", "disconnected_at", "updated_by", "updated_at"])

    def get_access_token(self, provider: str) -> str:
        """Return a valid access token for `provider`, refreshing inline if near expiry.

        Concurrent callers on Postgres serialise on a `pg_advisory_xact_lock`
        keyed on the credential id, so we never double-refresh. On SQLite
        (test environment) the lock call is skipped.
        """
        try:
            credential = OAuthCredential.objects.get(provider=provider, is_active=True)
        except OAuthCredential.DoesNotExist as exc:
            raise OAuthNotConnectedError(
                f"No active OAuth credential for provider={provider}"
            ) from exc

        if not self._near_expiry(credential):
            return credential.access_token

        with transaction.atomic():
            self._advisory_lock(credential.pk)
            # Re-fetch inside the lock — another worker may have refreshed.
            credential.refresh_from_db()
            if not self._near_expiry(credential):
                return credential.access_token
            self._refresh(credential)
            return credential.access_token

    # --- internals ---------------------------------------------------------

    def _validate_state(self, provider: str, state: str, actor: User) -> None:
        try:
            unsigned = _signer().unsign(state, max_age=STATE_MAX_AGE_SECONDS)
        except SignatureExpired as exc:
            raise OAuthStateError("OAuth state token has expired.") from exc
        except BadSignature as exc:
            raise OAuthStateError("OAuth state token is invalid.") from exc
        if unsigned != _state_payload(provider, actor.pk or 0):
            raise OAuthStateError("OAuth state token does not match actor/provider.")

    def _persist_new_credential(
        self,
        provider: str,
        payload: TokenPayload,
        actor: User,
    ) -> OAuthCredential:
        now = timezone.now()
        with transaction.atomic():
            OAuthCredential.objects.filter(provider=provider, is_active=True).update(
                is_active=False,
                disconnected_at=now,
                updated_by=actor,
                updated_at=now,
            )
            credential = OAuthCredential.objects.create(
                provider=provider,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                token_type=payload.token_type,
                expires_at=now + timedelta(seconds=payload.expires_in),
                scope=payload.scope,
                account_id=payload.account_id,
                connected_by=actor,
                connected_at=now,
                is_active=True,
                meta=payload.meta or {},
                created_by=actor,
                updated_by=actor,
            )
        return credential

    def _near_expiry(self, credential: OAuthCredential) -> bool:
        return credential.expires_at <= timezone.now() + REFRESH_WINDOW

    def _advisory_lock(self, credential_id: int) -> None:
        """Postgres-only advisory lock keyed on the credential id.

        On SQLite (used in tests) we skip the call — there's no equivalent
        and the lock is only there to serialise concurrent refresh workers.
        """
        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [credential_id])

    def _refresh(self, credential: OAuthCredential) -> None:
        """Refresh `credential.access_token` against the provider.

        The wire call is wired in alongside the live provider integration.
        The orchestration around it (lock, atomicity, expiry write-back)
        lives here so it can be tested independently.
        """
        raise NotImplementedError(
            f"OAuthService._refresh for provider={credential.provider} is wired in v1.1"
        )


def _default_token_exchange(provider: str, code: str) -> TokenPayload:
    """Placeholder token exchange — raises until the provider-specific call lands.

    Tests inject a stub via `OAuthService.complete(..., token_exchange=...)`
    rather than monkey-patching the HTTP layer. See `08-integrations.md`.
    """
    raise NotImplementedError(
        f"Token exchange for provider={provider} is wired in v1.1; "
        "pass `token_exchange=` to OAuthService.complete() in tests."
    )
