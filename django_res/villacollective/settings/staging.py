"""Staging settings — Render. Production-equivalent security, seeding allowed."""

from __future__ import annotations

from .production import *  # noqa: F403

ENVIRONMENT = "staging"

# Staging is a throwaway demo DB — realistic fake data is expected here.
# (Mirrors the explicit SEED_DEV_ALLOWED toggle in dev.py / test.py.)
SEED_DEV_ALLOWED = True
