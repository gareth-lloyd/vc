"""The seed_dev production guardrail must be unbypassable."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@override_settings(SEED_DEV_ALLOWED=False)
def test_blocked_when_not_allowed() -> None:
    with pytest.raises(CommandError, match="SEED_DEV_ALLOWED is False"):
        call_command("seed_dev", stdout=StringIO())


@override_settings(SEED_DEV_ALLOWED=False)
def test_i_understand_does_not_bypass_block() -> None:
    with pytest.raises(CommandError):
        call_command("seed_dev", "--i-understand", stdout=StringIO())
