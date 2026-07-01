import type { TFunction } from "i18next";
import { assignLanes, bandEdges } from "@/lib/timeline/geometry";
import type {
  ChangeOverRule,
  Discount,
  Extra,
  PropertyService,
  RatePlan,
  RatePlanDetail,
} from "@/features/properties/schemas";

/** The six stacked concern lanes, top to bottom. */
export const LANE_KEYS = [
  "seasons",
  "rates",
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
  /** ISO date, nulls substituted with the window bounds so open-ended bands span the year. */
  dateFrom: string;
  dateTo: string;
  label: string;
  sourceId: number;
  /** Greedy sub-lane index for overlapping bands within the lane. */
  sublane: number;
  meta: BandMeta;
}

/**
 * The band's display title. Changeover bands translate their weekday enum;
 * everything else uses the source record's name. Shared by the band button's
 * aria-label and the popover heading so the two never drift.
 */
export function bandTitle(band: WorkbenchBand, t: TFunction<"properties">): string {
  return band.laneKey === "changeover"
    ? t(`changeover_days.${band.meta.weekday ?? ""}`)
    : band.label;
}

export interface LaneModel {
  key: LaneKey;
  bands: WorkbenchBand[];
}

export interface ToLanesInput {
  windowStart: Date;
  dayCount: number;
  /** ISO bounds used to substitute open-ended (null) band dates. */
  windowFrom: string;
  windowTo: string;
  seasons: RatePlan[];
  /** Season details (periods + bands) drive the rates lane; loading/absent → no rate bands. */
  seasonDetails: RatePlanDetail[];
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

  const isVisible = (dateFrom: string, dateTo: string) => {
    const { start, end } = bandEdges(dateFrom, dateTo, windowStart);
    return end > 0 && start < dayCount;
  };

  const buildLane = (laneKey: LaneKey, raw: RawBand[]): LaneModel => {
    const visible = raw.filter((b) => isVisible(b.dateFrom, b.dateTo));
    const lanes = assignLanes(visible.map((b) => bandEdges(b.dateFrom, b.dateTo, windowStart)));
    return {
      key: laneKey,
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
    dateTo: season.effective_to ?? windowTo,
    label: season.name,
    sourceId: season.id,
    meta: { currencyCode: season.currency_code ?? null, isActive: season.is_active ?? true },
  }));

  const rateBandsUntiered: RawBand[] = input.seasonDetails.flatMap((plan) =>
    (plan.periods ?? []).flatMap((period) => {
      const bands = period.bands ?? [];
      if (bands.length === 0) return [];
      // One figure per band: a band prices either nightly or weekly (its basis),
      // never both — flat-mapping both mixes per-night and per-week amounts into
      // one nonsensical range (e.g. €650 nightly and €4,550 weekly → "€650–€4,550").
      const prices = bands
        .map((r) => numeric(r.nightly) ?? numeric(r.weekly))
        .filter((v): v is number => v != null);
      return [
        {
          id: `period-${period.id}`,
          // GAP-056: the period owns the dates — no need to derive them from bands.
          dateFrom: period.date_from,
          dateTo: period.date_to,
          label: period.name || plan.name,
          sourceId: period.id,
          meta: {
            planId: plan.id,
            planName: plan.name,
            currencyCode: plan.currency_code ?? null,
            minPrice: prices.length ? Math.min(...prices) : null,
            maxPrice: prices.length ? Math.max(...prices) : null,
            hasPoa: bands.some((r) => r.is_poa),
          },
        },
      ];
    }),
  );

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
    dateTo: service.applies_to ?? windowTo,
    label: service.name,
    sourceId: service.id,
    meta: { copy: service.copy },
  }));

  const extraBands: RawBand[] = input.extras.map((extra) => ({
    id: `extra-${extra.id}`,
    dateFrom: extra.applies_from ?? windowFrom,
    dateTo: extra.applies_to ?? windowTo,
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
    dateTo: discount.valid_to ?? windowTo,
    label: discount.name,
    sourceId: discount.id,
    meta: {
      code: discount.code ?? null,
      amount: discount.amount ?? null,
      kind: discount.kind ?? discount.rule_kind ?? null,
    },
  }));

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
    buildLane("inclusions", inclusionBands),
    buildLane("extras", extraBands),
    buildLane("discounts", discountBands),
    buildLane("changeover", changeoverBands),
  ];
}
