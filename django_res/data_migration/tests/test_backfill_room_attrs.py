"""`backfill_room_attrs` — positives-only keyword pass over room prose (GAP-064).

Convenience enrichment, not a correctness dependency: source text is retained
on the Room, so a missed keyword loses nothing.
"""

from __future__ import annotations

from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command

from properties.factories import FeatureFactory, RoomFactory
from properties.models import Feature, Room, RoomAttribute, RoomAttributeAssignment

pytestmark = pytest.mark.django_db


def _room(description: str, **kwargs: object) -> Room:
    return cast(Room, RoomFactory(website_description=description, **kwargs))


def _call(*args: str) -> str:
    out = StringIO()
    call_command("backfill_room_attrs", *args, stdout=out)
    return out.getvalue()


def _slugs(room: Room) -> set[str]:
    return set(
        RoomAttributeAssignment.objects.filter(room=room).values_list("attribute__slug", flat=True)
    )


class TestKeywordAssignments:
    def test_creates_assignments_for_confident_matches(self) -> None:
        room = _room("King bed, air con, ceiling fan and a lovely sea view from the balcony.")
        out = _call()
        assert _slugs(room) == {"aircon", "ceiling_fan", "sea_view", "balcony"}
        assert "aircon" in out

    def test_never_creates_on_absence(self) -> None:
        room = _room("A simple twin room.")
        _call()
        assert _slugs(room) == set()

    def test_hair_conditioner_is_not_aircon(self) -> None:
        room = _room("Complimentary shampoo and hair conditioner provided.")
        _call()
        assert _slugs(room) == set()

    def test_unqualified_fridge_is_not_confident(self) -> None:
        room = _room("Guests may use the shared fridge in the communal kitchen.")
        _call()
        assert _slugs(room) == set()

    def test_idempotent_on_rerun(self) -> None:
        room = _room("Air conditioning throughout.")
        _call()
        _call()
        assert RoomAttributeAssignment.objects.filter(room=room).count() == 1

    def test_reports_per_slug_counts(self) -> None:
        _room("Terrace with mini fridge.")
        out = _call()
        assert "terrace" in out
        assert "mini_fridge" in out


class TestEnsuiteFacet:
    def test_sets_shower_from_prose_and_flags_is_ensuite(self) -> None:
        room = _room("En-suite shower room with rain head.", is_ensuite=False)
        _call()
        room.refresh_from_db()
        assert room.ensuite_type == "shower"
        assert room.is_ensuite is True

    def test_sets_both_when_bath_and_shower(self) -> None:
        room = _room("Ensuite bathroom with bath and walk-in shower.")
        _call()
        room.refresh_from_db()
        assert room.ensuite_type == "both"

    def test_bathrobes_do_not_upgrade_shower_to_both(self) -> None:
        room = _room("En-suite shower room with bathrobes and bath towels provided.")
        _call()
        room.refresh_from_db()
        assert room.ensuite_type == "shower"

    def test_bath_words_outside_the_ensuite_sentence_are_ignored(self) -> None:
        room = _room("En-suite shower room. A bath is available in the family bathroom.")
        _call()
        room.refresh_from_db()
        assert room.ensuite_type == "shower"

    def test_never_downgrades_an_existing_type(self) -> None:
        room = _room("En-suite shower.", ensuite_type="bath", is_ensuite=True)
        _call()
        room.refresh_from_db()
        assert room.ensuite_type == "bath"

    def test_no_ensuite_mention_leaves_facets_alone(self) -> None:
        room = _room("Room with a shower shared with the neighbouring twin room.")
        _call()
        room.refresh_from_db()
        # "en-suite" never appears, so nothing is inferred even though
        # "shower" does.
        assert room.ensuite_type == ""
        assert room.is_ensuite is False


class TestPlacementNoteSource:
    """GAP-065 — the crammed amenity facts in the preserved legacy placement
    string ("First floor - King, hairdryer") get re-homed by the same pass."""

    def test_amenities_only_in_placement_note_are_assigned(self) -> None:
        room = cast(Room, RoomFactory(placement_note="First floor - King, hairdryer"))
        assert room.website_description == ""
        _call()
        assert _slugs(room) == {"hairdryer"}

    def test_note_and_description_both_contribute(self) -> None:
        room = _room(
            "Lovely sea view.",
            placement_note="Ground floor. Mini fridge, safe",
        )
        _call()
        assert _slugs(room) == {"sea_view", "mini_fridge"}

    def test_note_vocabulary_never_merges_into_a_description_sentence(self) -> None:
        # The sources are joined with a newline (a sentence boundary): an
        # en-suite mention trailing the description must not read shower/bath
        # words from the note.
        room = _room(
            "Master bedroom, en-suite",
            placement_note="Ground floor. Shower room nearby",
        )
        _call()
        room.refresh_from_db()
        assert room.ensuite_type == ""

    def test_idempotent_over_note_matches(self) -> None:
        room = cast(Room, RoomFactory(placement_note="Ground floor. Ceiling fan"))
        _call()
        _call()
        assert RoomAttributeAssignment.objects.filter(room=room).count() == 1

    def test_dry_run_counts_note_sourced_hits(self) -> None:
        cast(Room, RoomFactory(placement_note="First floor. Wifi and hair dryer"))
        out = _call("--dry-run")
        assert "would create" in out
        assert "1 x hairdryer" in out
        assert RoomAttributeAssignment.objects.count() == 0


class TestBedSizeBackfill:
    """GAP-066 — bed size (King / Super-king / Emperor) hand-typed into the
    same preserved prose gets re-homed onto `RoomBeds.double_size`. Positives
    only, gated on a present double bed, never overwriting a curated size."""

    def test_sets_super_king_from_placement_note(self) -> None:
        room = cast(Room, RoomFactory(placement_note="First floor. Superking bed."))
        _call()
        room.beds.refresh_from_db()
        assert room.beds.double_size == "super_king"

    def test_king_from_description(self) -> None:
        room = _room("Master bedroom with a King bed.")
        _call()
        room.beds.refresh_from_db()
        assert room.beds.double_size == "king"

    def test_super_king_wins_over_bare_king(self) -> None:
        # "Super king" contains a standalone "king"; the ordered scan must
        # return SUPER_KING, not KING.
        room = _room("Spacious room with a Super king bed.")
        _call()
        room.beds.refresh_from_db()
        assert room.beds.double_size == "super_king"

    def test_emperor_from_prose(self) -> None:
        room = _room("Emperor bed in the master suite.")
        _call()
        room.beds.refresh_from_db()
        assert room.beds.double_size == "emperor"

    def test_not_set_without_a_double_bed(self) -> None:
        # Size only qualifies a double; a room with no double bed is skipped
        # even if the prose mentions "king".
        room = _room("Twin room, King single beds.")
        room.beds.double = 0
        room.beds.save()
        _call()
        room.beds.refresh_from_db()
        assert room.beds.double_size == ""

    def test_never_overwrites_a_curated_size(self) -> None:
        room = _room("King bed.")
        room.beds.double_size = "emperor"
        room.beds.save()
        _call()
        room.beds.refresh_from_db()
        assert room.beds.double_size == "emperor"

    def test_dry_run_counts_but_writes_nothing(self) -> None:
        room = cast(Room, RoomFactory(placement_note="First floor. Emperor bed."))
        out = _call("--dry-run")
        assert "emperor" in out
        room.beds.refresh_from_db()
        assert room.beds.double_size == ""


class TestSyncReinvocation:
    def test_links_implications_once_features_exist(self) -> None:
        feature = cast(Feature, FeatureFactory(slug="sea-view"))
        assert RoomAttribute.objects.get(slug="sea_view").implies_property_feature is None
        _call()
        assert RoomAttribute.objects.get(slug="sea_view").implies_property_feature == feature


class TestDryRun:
    def test_dry_run_writes_nothing_but_reports(self) -> None:
        room = _room("Air con and balcony.", is_ensuite=False)
        out = _call("--dry-run")
        assert "aircon" in out
        assert _slugs(room) == set()
        room.refresh_from_db()
        assert room.ensuite_type == ""

    def test_dry_run_previews_the_same_matches_as_a_real_run(self) -> None:
        # The catalog ensure (sync) runs in both modes so a dry-run can never
        # under-report against a missing/partial catalog.
        room = _room("Terrace with air con.")
        RoomAttribute.objects.filter(slug="aircon").delete()
        out = _call("--dry-run")
        assert "1 x aircon" in out
        assert _slugs(room) == set()
