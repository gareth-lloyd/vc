"""Storage aliases for reservations file fields (GAP-094).

`FileField(storage=...)` accepts a callable, evaluated lazily and serialised
into migrations by dotted path — so it must be a module-level function, never
a lambda or a resolved storage object (which would freeze the *test/dev*
backend into the migration file).
"""

from __future__ import annotations

from django.core.files.storage import Storage, storages


def documents_storage() -> Storage:
    """The private `documents` alias — never URL-served; see settings.base."""
    return storages["documents"]
