# Owner / loader question round — 2026-07-02

Feeds tickets **Q-019** (room attributes), **Q-021** (defaults + feature
wording), **Q-022** (season labels), **Q-023** (odd-length stay pricing).
Written to be pasted into an email to Nick & Bryony (or used as a Loom
brief) as-is from "Hi both" down. Answers get recorded per ticket and in
`10-decisions.md`; retire this file to `done/` when the round closes.

Format follows the 2026-06-11 email round: each question is numbered, has a
**suggested answer** so a one-word "yes" per number is a complete reply, and
nothing here blocks anything you can't see — it's all "what should the new
system say/do", not "how".

---

Hi both,

Four short topics from building the new system — mostly confirming things
you already do by habit so the system can do them for you. Reply by number;
"yes" is a fine answer anywhere you agree with the suggestion.

## A. Room details (for Bryony)

When you set up rooms today you type the same facts in a fixed order from
memory (bed type, "ensuite shower", air con, then sea view / balcony /
terrace when known). We're turning those into proper tick-boxes and fields
so they're consistent, searchable, and only need entering once.

**A1 — Is this the complete list of room facts worth capturing?**
Ensuite (shower / bath / both) · air conditioning · sea view · balcony ·
terrace · outside access · wheelchair accessible · floor/level. What's
missing that you find yourself typing — e.g. interconnecting rooms?
Ground-floor access? Anything else?
*(Bed types and counts are already structured; your internal-only notes for
unadvertisable facts — pull-out child beds, shared bathrooms, mosquito
screens — stay exactly as they are.)*

**A2 — How should we label floors?**
Suggested: a fixed list — *Lower ground / Ground / First / Second / Third+*.
Or would you rather free numbering? (Whatever you pick, the rooms list will
group same-floor rooms together automatically, so you no longer have to
keep them adjacent by hand.)

**A3 — Should the public website change?**
Suggested: **no change for now** — the website keeps showing your written
descriptions exactly as today; the tick-boxes are internal (searching,
checking, and making sure nothing gets forgotten). We can switch the site to
neat icon lists later if you ever want that, but that's a separate look-and-
feel decision.

One bonus you get for free: ticking "wheelchair accessible" on a room will
prompt the villa-level accessibility feature automatically — no more
entering it in three places.

## B. New-villa defaults + feature wording (Nick & Bryony)

**B1 — Confirm the defaults every new villa starts with** (all changeable
per villa, this just saves re-typing): booking deposit **required, 30%** ·
security deposit **required, fixed amount** (amount entered per villa) ·
commission **percentage** · check-in **16:30** / check-out **10:30**.
Anything wrong or missing? (Changeover day and minimum nights vary too much
per villa, so those stay per-villa with no default.)

**B2 — Housekeeping frequency: what's the agreed wording?**
You flagged "daily" vs "6 days a week" as needing a decision. Suggested
option list: *Daily / 6 days a week / Every other day / Twice a week /
Weekly / On request*. Edit freely — whatever list you settle on becomes the
dropdown, so the hesitation disappears.

**B3 — Parking: which labels should exist?**
Today "Parking" and "Covered parking" both exist and you're never sure which
to pick. Suggested: **"Parking"** on any villa with parking, plus
**"Covered parking"** *additionally* when it's covered. OK? And while we're
at it — any other near-duplicate features that make you hesitate? We're
cleaning the whole list once, now.

**B4 — Confirm the "almost every villa" starter set.**
New villas would start with these pre-ticked (remove where untrue):
housekeeping · gardening · pool cleaning · kitchen · dining room · sitting
room. Right set?

## C. Season labels (Nick)

You've already told us how seasons should work: prices are per week, and
you label bunches of weeks as a season for reporting ("peak-season bookings
up X%") and pricing decisions ("20% off from peak to high"). Each villa
keeps its own dates — the labels are what line up across villas.

**C1 — Confirm the fixed label list.**
Suggested: **Top peak / Peak / High / Shoulder / Low** — five labels, used
by every villa, each villa deciding which of its weeks carry which label.
Two checks: (a) any label missing or surplus? (b) for a villa that charges
the same rate all year — is labelling everything one tier (or leaving weeks
unlabelled) acceptable, or do you want a *Standard* label for those?

## D. Pricing odd-length stays (Nick)

You raised nightly pricing for odd bookings (10–15 nights that don't fit
week blocks) and worry about rounding. Rounding is settled — everything is
computed to the penny with bankers' rounding — so this is just confirming
the composition rule matches what you'd expect.

**D1 — How a non-whole-week stay is priced.**
Current rule: every night is priced at that week's weekly price ÷ 7, and the
nights are added up. So a 10-night stay spanning two rate weeks = 7 nights
at the first week's rate ÷ 7 + 3 nights at the second week's ÷ 7. The
alternative would be "1 × full weekly price + 3 nights at a separate nightly
rate". Suggested: **keep the current rule** — it never surprises anyone when
a stay crosses a season boundary. OK?

**D2 — When you've set an explicit nightly price.**
Where a period has its own nightly price entered, that price is used for the
nights (instead of weekly ÷ 7). Confirm that's the behaviour you want.

**D3 — Any floor on odd lengths?**
Each villa's minimum-nights rules always apply. Beyond that, is there any
blanket rule like "never quote under 5 nights", or is villa minimum-nights
the only guard? Suggested: **villa minimum-nights only**.

Thanks — short answers by number are perfect.

---

## Bookkeeping (internal)

| # | Feeds | On answer |
|---|---|---|
| A1–A3 | Q-019 | attribute set + floor vocab + rendering posture → model/migration/RoomFormDialog build can start (jointly with the GAP-024 posture, already relaxed for `beds`) |
| B1 | Q-021 (seeding half) | seed `GroupFinance`/`GroupSettings` values — buildable already, B1 only confirms |
| B2–B4 | Q-021 (vocabulary half) | `Feature` seed list curation + housekeeping-frequency shape |
| C1 | Q-022 | `season_tier` controlled enum, attached at the rate-period level, copies with the base on carry-over (Q-018) |
| D1–D3 | Q-023 | bless current engine behaviour in `04-pricing.md` + pin 10/15-night tests — docs/tests can proceed ahead of the answer; D-answers only confirm |
