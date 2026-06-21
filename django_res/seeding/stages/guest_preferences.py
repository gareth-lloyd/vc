"""Attach typed preferences (bed type, dietary, ...) to a slice of customers."""

from __future__ import annotations

from seeding.context import SeedContext
from seeding.registry import Stage, register


def _run(ctx: SeedContext) -> int:
    if not ctx.knobs.pct_preference:
        return 0
    from accounts.enums import PersonKind
    from accounts.models import Person
    from reservations.models.preferences import GuestPreference, GuestPreferenceType

    names = [
        "Twin beds preferred",
        "Vegetarian",
        "Allergic to nuts",
        "Cot required",
        "Pet-friendly",
        "Early arrival OK",
    ]
    types = [GuestPreferenceType.objects.get_or_create(name=name)[0] for name in names]
    pool_pks = [c.pk for c in ctx.guest_pool]
    candidates = (
        list(
            Person.objects.filter(kind=PersonKind.CUSTOMER.value)
            .exclude(pk__in=pool_pks)
            .values_list("pk", flat=True)[:50]
        )
        + pool_pks
    )
    target = max(1, int(len(candidates) * ctx.knobs.pct_preference))
    chosen = ctx.rng.sample(candidates, k=min(target, len(candidates)))
    made = 0
    for pk in chosen:
        customer = Person.objects.get(pk=pk)
        for pref_type in ctx.rng.sample(types, k=ctx.rng.randint(1, 2)):
            _, created = GuestPreference.objects.get_or_create(
                person=customer,
                preference_type=pref_type,
                quotation=None,
                defaults={"notes": ""},
            )
            if created:
                made += 1
    return made


register(Stage(name="guest_preferences", run=_run, depends_on=("bookings",)))
