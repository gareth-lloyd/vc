"""Storage aliases for reservations file fields (GAP-094).

`FileField(storage=...)` accepts a callable, evaluated lazily and serialised
into migrations by dotted path — so it must be a module-level function, never
a lambda or a resolved storage object (which would freeze the *test/dev*
backend into the migration file).
"""

from __future__ import annotations

from botocore.exceptions import ClientError
from django.core.files.storage import Storage, storages


def documents_storage() -> Storage:
    """The private `documents` alias — never URL-served; see settings.base."""
    return storages["documents"]


# Reading a stored document can fail in three shapes, and all three mean the
# same thing to a caller: these bytes cannot be served, so offer "regenerate".
#
# `ClientError` is the one worth spelling out. django-storages translates only
# an HTTP **404** into `FileNotFoundError` (`backends/s3.py:618`, `:529`,
# `:582`) and re-raises everything else — but under the bucket policy the
# documents bucket runs (`s3:GetObject` granted, `s3:ListBucket` **not**) S3
# answers a *missing* key with **403 AccessDenied**. So the 404 branch, which
# is the only one the local FileSystemStorage tests can exercise, is close to
# unreachable in production: the ordinary "someone deleted the object" case
# arrives as a `ClientError`.
#
# That collapses the distinction between "gone" and "S3 is unhappy", and the
# tie goes to reporting it as missing. A transient outage misreported as a
# missing file costs an operator one Generate click that fails just as loudly;
# a permanently-missing object misreported as a 500 leaves them with no
# explanation and no route back to a working document.
#
# `ValueError` is a row whose `FileField` is empty. Mirrors
# `comms.signals._ATTACHMENT_READ_ERRORS`, which reads the same objects.
DOCUMENT_READ_ERRORS = (OSError, ValueError, ClientError)
