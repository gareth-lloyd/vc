import type { TFunction } from "i18next";
import { assignLanes, bandEdges } from "@/lib/timeline/geometry";
import { addDaysIso } from "@/lib/format/date";
import type {
  ChangeOverRule,
  Discount,
  Extra,
  PropertyService,
  RatePlan,
  RatePlanDetail,
} from "@/features/properties/schemas";
import { periodLabel } from "@/features/properties/periodLabel";
import { coverageDateGaps } from "./coverageGaps";

/** The stacked concern lanes, top to bottom. `coverage` is derived (the
 * selected plan's unpriced dates) and only present when a plan is selected. */
export const LANE_KEYS = [
  "seasons",
  "rates",
  "coverage",
  "inclusions",
  "extras",
  "discounts",
  "changeover",
] as const;
export type LaneKey = (typeof LANE_KEYS)[number];

/**
 * Per-band presentational payload. One flat, fully-optional bag rather than a
 * per-lane discriminated union — the render sites read only the fields their
 * lane populates. Typed (not `Record<string, unknown>`) so the producer here
 * and the `BandDetail` consumer share a checked contract: a renamed/dropped
 * field is a compile error, not a silent `undefined` in the popover.
 */
export interface BandMeta {
  /** Seasons + rates + extras: currency for money formatting. */
  currencyCode?: string | null;
  isActive?: boolean;
  planId?: number;
  planName?: string;
  /** Rates: min/max across the period's bands (single price basis per band). */
  minPrice?: number | null;
  maxPrice?: number | null;
  hasPoa?: boolean;
  /** Rates: the period exists but has no bands yet — rendered as an outline. */
  noRates?: boolean;
  /** Rates: prefill for the "add a period after this one" affordance — absent
   * when the plan's next period is contiguous (a create there can never pass
   * the DB EXCLUDE) or when the period runs past the window (its band is
   * clamped, so a "+" would sit visually mid-period). `date_to` caps the
   * range at the day before the plan's next period, when one exists. */
  addAfter?: { date_from: string; date_to?: string };
  /** Coverage: an unpriced gap in the selected plan (clickable for writers). */
  isGap?: boolean;
  /**
   * Rates: global price tier (tertile of `minPrice` across the whole rates
   * lane), driving tone intensity so stacked cards read as cheap→expensive.
   * Absent for all-POA cards (no numeric price) → they fall back to lane tone.
   */
  priceTier?: "low" | "mid" | "high";
  /** Inclusions: the guest-facing service copy. */
  copy?: string | null;
  /** Extras. */
  isMandatory?: boolean;
  amount?: string | null;
  /** Discounts. */
  code?: string | null;
  kind?: string | null;
  /** Changeover: the weekday enum value (drives the translated label). */
  weekday?: string;
}

export interface WorkbenchBand {
  id: string;
  laneKey: LaneKey;
  /** ISO dates, both INCLUSIVE (the backend convention), nulls substituted
   * with the window bounds so open-ended bands span the year. Display sites
   * (aria labels, popovers) use these raw. */
  dateFrom: string;
  dateTo: string;
  /** `dateTo + 1`, the band's EXCLUSIVE end. Geometry (`bandGeometry`,
   * `bandEdges`) treats its end as exclusive, so every geometry call must use
   * this — computed once here so render sites can't drift from the culling
   * and sub-lane packing below. */
  dateToExclusive: string;
  label: string;
  sourceId: number;
  /** Greedy sub-lane index for overlapping bands within the lane. */
  sublane: number;
  meta: BandMeta;
}

/**
 * The band's display title. Changeover bands translate their weekday enum,
 * coverage gaps announce the absence ("No rates") rather than the plan name;
 * everything else uses the source record's name. Shared by the band button's
 * aria-label and the popover heading so the two never drift.
 */
export function bandTitle(band: WorkbenchBand, t: TFunction<"properties">): string {
  if (band.meta.isGap) return t("rate_workbench.coverage.gap_title");
  return band.laneKey === "changeover"
    ? t(`changeover_days.${band.meta.weekday ?? ""}`)
    : band.label;
}

export interface LaneModel {
  key: LaneKey;
  bands: WorkbenchBand[];
  /** Coverage lane only: the annotated plan's name, interpolated into the lane label. */
  planName?: string;
}

export interface ToLanesInput {
  windowStart: Date;
  dayCount: number;
  /** ISO bounds used to substitute open-ended (null) band dates. */
  windowFrom: string;
  windowTo: string;
  seasons: RatePlan[];
  /** Season details (periods + bands) drive the rates lane; loading/absent → no rate bands. */
  ratePlanDetails: RatePlanDetail[];
  /** The matrix's selected plan: when its detail is loaded, a derived coverage
   * lane shows the dates that plan does not price. */
  coveragePlanId?: number | null;
  services: PropertyService[];
  extras: Extra[];
  discounts: Discount[];
  changeover: ChangeOverRule[];
}

interface RawBand {
  id: string;
  dateFrom: string;
  dateTo: string;
  label: string;
  sourceId: number;
  meta: BandMeta;
}

const numeric = (value: string | null | undefined): number | null => {
  if (value == null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/**
 * Assemble the six concern lanes for a property's whole-year timeline. Pure —
 * takes already-fetched collections and the window, returns positioned-ready
 * band models (geometry/culling happens at render via `bandGeometry`). Bands
 * that fall entirely outside the window are dropped so sub-lane packing only
 * reflects what's visible.
 */
export function toLanes(input: ToLanesInput): LaneModel[] {
  const { windowStart, dayCount, windowFrom, windowTo } = input;
  // `windowTo` is exclusive (next Jan 1); the last INCLUSIVE window date is
  // what open-ended band dates substitute — band dates are inclusive.
  const windowLast = addDaysIso(windowTo, -1);

  // Band dates are inclusive but the geometry treats its end as an exclusive
  // edge, so edges are computed on `dateTo + 1`: a single-day band gets width,
  // contiguous periods kiss instead of leaving a phantom one-day slit, and
  // bands sharing a boundary day genuinely overlap (they stack).
  const withEnd = (b: RawBand) => ({ ...b, dateToExclusive: addDaysIso(b.dateTo, 1) });
  const edges = (b: RawBand & { dateToExclusive: string }) =>
    bandEdges(b.dateFrom, b.dateToExclusive, windowStart);

  const buildLane = (laneKey: LaneKey, raw: RawBand[], planName?: string): LaneModel => {
    const visible = raw.map(withEnd).filter((b) => {
      const { start, end } = edges(b);
      return end > 0 && start < dayCount;
    });
    const lanes = assignLanes(visible.map(edges));
    return {
      key: laneKey,
      planName,
      bands: visible.map((b, i) => ({
        ...b,
        laneKey,
        sublane: lanes[i],
      })),
    };
  };

  const seasonBands: RawBand[] = input.seasons.map((season) => ({
    id: `season-${season.id}`,
    dateFrom: season.effective_from ?? windowFrom,
    dateTo: season.effective_to ?? windowLast,
    label: season.name,
    sourceId: season.id,
    meta: { currencyCode: season.currency_code ?? null, isActive: season.is_active ?? true },
  }));

  const rateBandsUntiered: RawBand[] = input.ratePlanDetails.flatMap((plan) => {
    const periods = plan.periods ?? [];
    return periods.map((period) => {
      // A zero-band period still occupies its dates (the DB EXCLUDE reserves
      // them), so it renders as a "no rates yet" outline rather than vanishing.
      const bands = period.bands ?? [];
      // One figure per band: a band prices either nightly or weekly (its basis),
      // never both — flat-mapping both mixes per-night and per-week amounts into
      // one nonsensical range (e.g. €650 nightly and €4,550 weekly → "€650–€4,550").
      const prices = bands
        .map((r) => numeric(r.nightly) ?? numeric(r.weekly))
        .filter((v): v is number => v != null);
      // "Add a period after this one" prefill, scoped to the OWNING plan:
      // the free range runs from the day after this period to the day before
      // the plan's next one. A contiguous successor leaves no free day, so no
      // prefill — the affordance is suppressed rather than offering a create
      // the DB EXCLUDE is guaranteed to reject. Plan periods never overlap
      // (same EXCLUDE), so the earliest start after this period IS the next.
      const nextFrom = periods.reduce<string | null>(
        (min, p) =>
          p.date_from > period.date_to && (min == null || p.date_from < min) ? p.date_from : min,
        null,
      );
      const dayAfter = addDaysIso(period.date_to, 1);
      // A period running past the window renders clamped at the window edge,
      // so its "+" would sit visually mid-period and prefill an offscreen
      // date — suppressed; view next year to extend it. Ending exactly on the
      // window's last day is fine: the true end is visible.
      const addAfter =
        nextFrom === dayAfter || period.date_to > windowLast
          ? undefined
          : {
              date_from: dayAfter,
              ...(nextFrom != null ? { date_to: addDaysIso(nextFrom, -1) } : {}),
            };
      return {
        id: `period-${period.id}`,
        // GAP-056: the period owns the dates — no need to derive them from bands.
        dateFrom: period.date_from,
        dateTo: period.date_to,
        label: periodLabel(period),
        sourceId: period.id,
        meta: {
          planId: plan.id,
          planName: plan.name,
          currencyCode: plan.currency_code ?? null,
          minPrice: prices.length ? Math.min(...prices) : null,
          maxPrice: prices.length ? Math.max(...prices) : null,
          hasPoa: bands.some((r) => r.is_poa),
          noRates: bands.length === 0,
          addAfter,
        },
      };
    });
  });

  // Rank ALL rate cards across the whole lane by min price into global tertiles,
  // so overlapping cards get distinct tone intensities regardless of which plan
  // they belong to (a per-plan ranking would flatten every single-card plan to
  // one tier). We tier over the *distinct* prices and only when there are at
  // least three of them: with fewer, tertiles are meaningless (a lone card would
  // always read "high", two prices would never yield "low", and tied prices
  // would collapse to one tier) — so those cases stay untiered and fall back to
  // the neutral lane tone. All-POA cards have no numeric price and stay untiered.
  const distinctPrices = [
    ...new Set(rateBandsUntiered.map((b) => b.meta.minPrice).filter((v): v is number => v != null)),
  ].sort((a, b) => a - b);
  const tierFor = (price: number | null | undefined): BandMeta["priceTier"] => {
    if (price == null || distinctPrices.length < 3) return undefined;
    const q1 = distinctPrices[Math.floor(distinctPrices.length / 3)];
    const q2 = distinctPrices[Math.floor((distinctPrices.length * 2) / 3)];
    return price < q1 ? "low" : price < q2 ? "mid" : "high";
  };
  const rateBands: RawBand[] = rateBandsUntiered.map((b) => ({
    ...b,
    meta: { ...b.meta, priceTier: tierFor(b.meta.minPrice) },
  }));

  const inclusionBands: RawBand[] = input.services.map((service) => ({
    id: `service-${service.id}`,
    dateFrom: service.applies_from ?? windowFrom,
    dateTo: service.applies_to ?? windowLast,
    label: service.name,
    sourceId: service.id,
    meta: { copy: service.copy },
  }));

  const extraBands: RawBand[] = input.extras.map((extra) => ({
    id: `extra-${extra.id}`,
    dateFrom: extra.applies_from ?? windowFrom,
    dateTo: extra.applies_to ?? windowLast,
    label: extra.name,
    sourceId: extra.id,
    meta: {
      isMandatory: extra.is_mandatory ?? false,
      amount: extra.amount ?? null,
      currencyCode: extra.currency_code ?? null,
    },
  }));

  const discountBands: RawBand[] = input.discounts.map((discount) => ({
    id: `discount-${discount.id}`,
    dateFrom: discount.valid_from ?? windowFrom,
    dateTo: discount.valid_to ?? windowLast,
    label: discount.name,
    sourceId: discount.id,
    meta: {
      code: discount.code ?? null,
      amount: discount.amount ?? null,
      kind: discount.kind ?? discount.rule_kind ?? null,
    },
  }));

  // Coverage: the selected plan's unpriced dates, as clickable gap bands.
  // Only meaningful once that plan's detail (periods) has loaded, and only
  // when the plan's effective range touches the window at all — otherwise the
  // empty lane would falsely read "no gaps" for a year the plan never prices.
  const selectedPlan =
    input.coveragePlanId != null
      ? (input.ratePlanDetails.find((p) => p.id === input.coveragePlanId) ?? null)
      : null;
  const coveragePlan =
    selectedPlan &&
    !(selectedPlan.effective_to && selectedPlan.effective_to < windowFrom) &&
    !(selectedPlan.effective_from && selectedPlan.effective_from > windowLast)
      ? selectedPlan
      : null;
  const coverageBands: RawBand[] = coveragePlan
    ? coverageDateGaps({
        periods: coveragePlan.periods ?? [],
        windowFrom,
        windowTo,
        effectiveFrom: coveragePlan.effective_from,
        effectiveTo: coveragePlan.effective_to,
      }).map((gap) => ({
        id: `coverage-${gap.from}`,
        dateFrom: gap.from,
        dateTo: gap.to,
        label: coveragePlan.name,
        sourceId: coveragePlan.id,
        meta: { isGap: true, planId: coveragePlan.id, planName: coveragePlan.name },
      }))
    : [];

  const changeoverBands: RawBand[] = input.changeover.map((rule) => ({
    id: `changeover-${rule.id}`,
    dateFrom: rule.effective_from,
    dateTo: rule.effective_to,
    label: rule.weekday,
    sourceId: rule.id,
    meta: { weekday: rule.weekday },
  }));

  return [
    buildLane("seasons", seasonBands),
    buildLane("rates", rateBands),
    // Directly under the rates it annotates. Present even when gap-free —
    // an empty coverage lane reads as "fully priced", which is the feedback.
    ...(coveragePlan ? [buildLane("coverage", coverageBands, coveragePlan.name)] : []),
    buildLane("inclusions", inclusionBands),
    buildLane("extras", extraBands),
    buildLane("discounts", discountBands),
    buildLane("changeover", changeoverBands),
  ];
}
