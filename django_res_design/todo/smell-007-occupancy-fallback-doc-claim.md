# SMELL-007 — Occupancy out-of-range: spec misstates what legacy did

- **Severity:** 🟡 Smell (doc inaccuracy — no code wrong, but the spec lies)
- **Source:** 2026-06-02 audit of the legacy quote path (`sp_getQuotationData`
  turned out to be a search proc; real logic is `ResService.cs:ProcessQuotationItemAsync`
  + `RatesModel.Calculate()`).
- **Files:**
  - `django_res_design/04-pricing.md` (`#### Occupancy bracket: matched, not defaulted-to-highest`, ~line 314)
  - `django_res_design/09-departures.md` ("Legacy correctness bugs explicitly fixed" table, row #2, ~line 211)

## Problem

Both docs assert the legacy quote engine **"defaulted to the highest occupancy
bracket when occupancy was ambiguous,"** over-quoting small parties. That is not
what the code does. When a party matches no occupancy band, legacy falls back to
the **base weekly rate ÷ 7**, not a highest bracket:

```csharp
// ResService.cs:2117-2134
OccupancyPrice occupiesObj = pricePerPerson.FirstOrDefault(
    x => args.Guests >= x.OccupencyFrom && args.Guests <= x.OccupencyTo);
if (occupiesObj != null)
    weeklyPrice += occupiesObj.NightlyPrice;
else
{
    priceObj.Calculate();
    weeklyPrice += priceObj.WeeklyPrice / 7;   // <-- base rate, NOT highest bracket
}
```

The rewrite's decision (raise `PartyOutOfRange`) is fine and stays. Only the
"what legacy did" justification is false — and a false legacy claim is a trap for
anyone doing cutover reconciliation or trusting the spec to rebuild a behaviour.

## Proposed fix

Doc-only:
- `04-pricing.md`: replace "defaulted to the highest occupancy bracket when
  occupancy was ambiguous — over-quoting for small parties" with the accurate
  description — legacy fell back to the **base weekly rate (`WeeklyPrice ÷ 7`)**
  when the party matched no band. Keep the conclusion sentence (rewrite raises
  `PartyOutOfRange`; not preserved under any flag).
- `09-departures.md` row #2: correct the *Bug* cell the same way; the *New
  behaviour* cell is unchanged.

No engine change. Historical quotes are frozen in `Booking.pricing_snapshot`, so
there is no migration impact.

## Acceptance

- Neither doc claims "highest bracket".
- `grep -ri "highest occupancy bracket" django_res_design/` is clean.
- The rewrite's `PartyOutOfRange` behaviour is unchanged.

## Dependencies

- None. Pairs with [BUG-009](bug-009-price-basis-ignored-by-engine.md) and the
  GAP-007/008 parity tickets as the output of the same pricing audit.
