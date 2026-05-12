"""Session listing + revocation helpers over django_session + UserSession."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserSession


@dataclass(frozen=True)
class SessionInfo:
    session_key: str
    created_at: datetime
    last_seen_at: datetime
    user_agent: str
    ip: str | None


class SessionService:
    @staticmethod
    def list_for_user(user: User) -> list[SessionInfo]:
        rows = UserSession.objects.filter(user=user, revoked_at__isnull=True).order_by(
            "-last_seen_at"
        )
        return [
            SessionInfo(
                session_key=row.session_key,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                user_agent=row.user_agent,
                ip=row.ip,
            )
            for row in rows
        ]

    @staticmethod
    @transaction.atomic
    def revoke(session_key: str) -> None:
        Session.objects.filter(session_key=session_key).delete()
        UserSession.objects.filter(session_key=session_key).update(revoked_at=timezone.now())

    @classmethod
    @transaction.atomic
    def revoke_all_for_user(cls, user: User, *, except_current: str | None = None) -> int:
        rows = UserSession.objects.filter(user=user, revoked_at__isnull=True)
        if except_current:
            rows = rows.exclude(session_key=except_current)
        keys = list(rows.values_list("session_key", flat=True))
        Session.objects.filter(session_key__in=keys).delete()
        rows.update(revoked_at=timezone.now())
        return len(keys)
