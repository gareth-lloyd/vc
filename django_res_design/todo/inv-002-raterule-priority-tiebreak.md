# INV-002 — `RateRule.priority` tie-break behaviour

- **Status:** ✅ **CLOSED** (2026-05-27 critique) — deterministic and
  tested. `pricing/services/rates.py::pick_rule_for_night` orders by
  `priority` desc, then by `rule_specificity` (narrower range wins on
  tie). Both branches are pinned by
  `test_engine.py::test_quote_tiebreak_higher_priority_wins` and
  `::test_quote_tiebreak_equal_priority_narrower_range_wins`.
- **Severity:** Investigation
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` "What I'd
  want to investigate further" item 2

## Question

Overlapping rules are explicitly allowed — the `priority` field implies
tie-breaking. The pricing engine must read the highest-priority match.

- Does the engine actually order by priority?
- Is it tested?
- What's the behaviour when two rules tie on priority and date range?

## Suggested probe

```
rg -n "order_by.*priority" django_res/pricing/
rg -n "priority" django_res/pricing/tests/
```

## Outcome

Either:

- Confirm there's a deterministic priority order + test pinning it.
- Or open a bug ticket: nondeterministic tie-break is a real correctness
  issue when applied to money.
