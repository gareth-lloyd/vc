"""Cross-app constants about `Person.legacy_id`.

GAP-118: these three values are minted by `data_migration` but *read* outside
it — `ContactSerializer.is_unknown_client` has to recognise the sentinel row,
and `accounts` sits at the bottom of the import spine, so it cannot import
`data_migration.loaders.sentinels` (an upward edge). They live here and
`sentinels.py` re-exports them, keeping the composition single-source: the
loader write, the `person_for_client` read, the `reconcile_legacy` count slices
and the API flag can never drift apart.
"""

from __future__ import annotations

# `legacy_id` minted on the sentinel rows.
UNKNOWN_LEGACY_ID = "__unknown__"

# Canonical `legacy_id` prefix for the customer Persons `ClientLoader` writes
# (`client-{VillaClientDetailsId}`).
CLIENT_LEGACY_PREFIX = "client-"

# Fixed legacy_id for the `unknown_client` sentinel Person. Carries the
# `client-` prefix so it sorts with the customer rows, but reconcile_legacy
# excludes it from BOTH Person count slices (owner/agent AND client) so the
# documented VillaClientDetails gap stays stable whether or not it's minted.
UNKNOWN_CLIENT_LEGACY_ID = f"{CLIENT_LEGACY_PREFIX}{UNKNOWN_LEGACY_ID}"
