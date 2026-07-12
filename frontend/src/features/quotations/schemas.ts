import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";
import { isPositiveMoney } from "@/lib/format/money";
import { nightsCount } from "@/lib/nights";
import {
  quotationStatusSchema,
  quotationStatusLabel,
  quotationListItemSchema,
  quotationLineSchema,
  type QuotationStatus,
} from "@/lib/domain/quotation";

// The quotation read-model (status enum/label, list item, line, detail) lives
// in @/lib/domain/quotation so enquiries can embed it without a feature cycle
// (GAP-063). Re-exported here so intra-feature consumers keep one import path.
export {
  quotationStatusSchema,
  quotationStatusLabel,
  quotationListItemSchema,
  quotationLineSchema,
  quotationDetailSchema,
  type QuotationStatus,
  type QuotationListItem,
  type QuotationLine,
  type QuotationDetail,
} from "@/lib/domain/quotation";

export const quotationStatusOptions = (): Array<{ value: QuotationStatus; label: string }> =>
  quotationStatusSchema.options.map((value) => ({ value, label: quotationStatusLabel(value) }));

// Statuses that block further transitions (no send, no withdraw).
export const TERMINAL_QUOTATION_STATUSES: readonly QuotationStatus[] = [
  "accepted",
  "cancelled",
  "expired",
] as const;

// ----------------------------------------------------------------------
// Quote builder schemas — criteria, search results, save payload.
// ----------------------------------------------------------------------

// Mirror of the backend's SEARCH_FLEX_MAX — the widest ± arrival flex the
// search-options endpoint accepts. The range form's window width maps to
// flex via ceil(W / 2), so the window caps at 2 * this.
export const SEARCH_FLEX_MAX = 21;

export const quoteCriteriaInputSchema = z
  .object({
    date_from: z.string().min(1, i18n.t("common:errors.field_required")),
    date_to: z.string().min(1, i18n.t("common:errors.field_required")),
    adults: z.number().int().min(1, i18n.t("quotations:schema_errors.at_least_one_adult")),
    children: z.number().int().min(0),
    country: z.string(),
    region: z.string(),
    min_bedrooms: z.number().int().min(0).nullable(),
    max_bedrooms: z.number().int().min(0).nullable(),
    q: z.string(),
    // ± days around the preferred dates (seeded from the enquiry's
    // flexibility_days). The backend derives the search window; the dates
    // above stay the client's true requested stay. Wide enough for a
    // multi-week sweep ("any week in June") while intake's flexibility_days
    // stays capped at 3.
    flex_days: z.number().int().min(0).max(SEARCH_FLEX_MAX),
  })
  .refine((v) => !v.date_from || !v.date_to || v.date_from < v.date_to, {
    path: ["date_to"],
    message: i18n.t("quotations:schema_errors.date_to_after_date_from"),
  });
export type QuoteCriteriaInput = z.infer<typeof quoteCriteriaInputSchema>;

// What the operator fills in (GAP-043): an arrival window + a preferred stay
// length in weeks, not a fixed stay. `searchFormToCriteria` (searchCriteria.ts)
// translates this to the unchanged `QuoteCriteriaInput` wire shape — the
// backend contract stays put. "Search Specific Date" (legacy IsSpecificDate)
// collapses the window to the exact `arrive_from`.
export const quoteSearchFormSchema = z
  .object({
    arrive_from: z.string().min(1, i18n.t("common:errors.field_required")),
    // Ignored (and hidden in the form) when `specific_date` is on, so it may
    // be empty then; the refines below enforce it otherwise.
    arrive_to: z.string(),
    // The PREFERRED length: the engine snaps each block to the winning card's
    // min/max_nights, and the per-cell nights in the results are authoritative.
    weeks: z.number().int().min(1, i18n.t("quotations:schema_errors.at_least_one_week")),
    specific_date: z.boolean(),
    adults: z.number().int().min(1, i18n.t("quotations:schema_errors.at_least_one_adult")),
    children: z.number().int().min(0),
    country: z.string(),
    region: z.string(),
    min_bedrooms: z.number().int().min(0).nullable(),
    max_bedrooms: z.number().int().min(0).nullable(),
    q: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.specific_date) return;
    if (!v.arrive_to) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["arrive_to"],
        message: i18n.t("common:errors.field_required"),
      });
      return;
    }
    if (v.arrive_to < v.arrive_from) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["arrive_to"],
        message: i18n.t("quotations:schema_errors.arrive_to_before_arrive_from"),
      });
      return;
    }
    // Window width W maps to flex_days = ceil(W / 2) (searchCriteria.ts), and
    // the backend rejects flex_days > SEARCH_FLEX_MAX — so the window caps at
    // twice that.
    if (nightsCount(v.arrive_from, v.arrive_to) > 2 * SEARCH_FLEX_MAX) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["arrive_to"],
        message: i18n.t("quotations:schema_errors.arrive_window_too_wide"),
      });
    }
  });
export type QuoteSearchForm = z.infer<typeof quoteSearchFormSchema>;

// One offerable stay block for a result — always ≥1 on a priced result; >1
// only when a fixed-changeover property's flexibility window admits several
// changeover-to-changeover blocks. `is_available` is an advisory snapshot
// (the manual line hold / booking conversion is the real guard); only the
// default block is priced
// up front — picking another fires a reprice.
export const stayOptionSchema = z.object({
  date_from: z.string(),
  date_to: z.string(),
  nights: z.number(),
  is_default: z.boolean(),
  is_available: z.boolean(),
});
export type StayOption = z.infer<typeof stayOptionSchema>;

// One occupancy bracket the builder renders as its own default-checked line
// (GAP-044 occupancy fan-out). Only emitted when the covering rate card has
// ≥2 brackets. `total` is null for a POA/no-rate band (`is_poa` or
// `error_code`) — the band still shows, flagged, never dropped. `adults` is
// the representative party the backend priced (= max(1, min_party)) and is
// what a saved line posts.
export const occupancyBandSchema = z.object({
  min_party: z.number(),
  max_party: z.number(),
  adults: z.number(),
  // Value fields mirror the sibling quoteOption fields: nullable + optional so a
  // single band that omits a key can't reject the whole search response.
  total: z.union([z.string(), z.number()]).nullable().optional(),
  // Q-018 rate reductions: what the band would have cost at the base rates
  // when the engine applied a reduction — powers the "reduced from" hint.
  total_before_reduction: z.union([z.string(), z.number()]).nullable().optional(),
  currency_code: z.string().nullable().optional(),
  is_projected: z.boolean().nullable().optional(),
  is_poa: z.boolean().nullable().optional(),
  error_code: z.string().nullable().optional(),
});
export type OccupancyBand = z.infer<typeof occupancyBandSchema>;

// One priced result row returned from the builder search. The server
// pricing breakdown is opaque — we surface only the headline total +
// any error code, the rest stays in the snapshot for line save.
export const quoteOptionSchema = z.object({
  property_id: z.number(),
  property_name: z.string(),
  // Disambiguators for the results card: distinct villas can share a
  // guest-facing display name, so the card also shows the internal name
  // (when it differs) and the capacity headline.
  internal_name: z.string().nullable().optional(),
  bedrooms: z.number().nullable().optional(),
  sleeps: z.number().nullable().optional(),
  property_slug: z.string().nullable().optional(),
  // GAP-078: geography for the picker's country → region grouping, plumbed
  // from the candidate row (the pricing response carries no geo). Nullable +
  // optional (NOT defaulted) so hand-built fixtures stay valid inputs.
  region_name: z.string().nullable().optional(),
  country_name: z.string().nullable().optional(),
  hero_image_url: z.string().nullable().optional(),
  available: z.boolean(),
  total: z.union([z.string(), z.number()]).nullable().optional(),
  // Q-018 rate reductions: the pre-reduction total when the engine quoted
  // reduced prices (spread through from the quote breakdown) — the builder
  // shows a muted "reduced from" hint next to the effective total.
  total_before_reduction: z.union([z.string(), z.number()]).nullable().optional(),
  currency: z.string().nullable().optional(),
  rate_subtotal: z.union([z.string(), z.number()]).nullable().optional(),
  nights: z.number().optional(),
  // The dates the engine actually priced — may differ from the requested
  // criteria when the arrival was nudged forward to the changeover day
  // (GAP-007). The builder displays these and flags the shift by comparing
  // them against the requested dates.
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  error_detail: z.string().nullable().optional(),
  // Plan/card metadata the engine breakdown carries (all optional so older
  // responses still parse): the winning plan's inclusion text, whether the
  // price moves with party size, the fixed changeover day code (null = any),
  // the winning card's stay-length bounds, and the projected-rates flag.
  inclusion: z.string().nullable().optional(),
  occupancy_pricing: z.boolean().nullable().optional(),
  changeover_day: z.string().nullable().optional(),
  min_nights: z.number().nullable().optional(),
  max_nights: z.number().nullable().optional(),
  is_projected: z.boolean().nullable().optional(),
  stay_options: z.array(stayOptionSchema).nullable().optional(),
  // GAP-044 occupancy fan-out: the occupancy brackets to render as separate
  // default-checked lines. Empty/absent for a single-band villa; nullable +
  // optional so older responses still parse.
  occupancy_bands: z.array(occupancyBandSchema).nullable().optional(),
  breakdown: z.unknown().optional(),
});
export type QuoteOption = z.infer<typeof quoteOptionSchema>;

// What a block reprice returns — the same flattened quote-entry shape, but
// the caller already holds the property context so only the pricing fields
// are parsed. Error entries keep the bulk error_code shape.
export const stayRepriceSchema = z.object({
  available: z.boolean().optional().default(false),
  total: z.union([z.string(), z.number()]).nullable().optional(),
  // Q-018 rate reductions: pre-reduction total for the repriced week, so the
  // "reduced from" hint survives a block reprice.
  total_before_reduction: z.union([z.string(), z.number()]).nullable().optional(),
  currency_code: z.string().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  // Set when the engine still nudged the arrival (GAP-007) — surfaced inline
  // so the picker never silently shows different dates than were clicked.
  changeover_shifted_from: z.string().nullable().optional(),
  inclusion: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  error_detail: z.string().nullable().optional(),
  // GAP-044b two-axis picker: a reprice for an occupancy-priced villa carries
  // the chosen week's occupancy brackets (the backend attaches them on every
  // return path, incl. out-of-bracket/POA). Absent for a flat-rate villa or an
  // older response; nullable + optional so those still parse.
  occupancy_bands: z.array(occupancyBandSchema).nullable().optional(),
});
export type StayReprice = z.infer<typeof stayRepriceSchema>;

// The stay a result line hands to the builder on Add: the chosen block's
// dates plus the pricing that block resolved to (the option's own price for
// the default block, a reprice for a picked alternative). Absent on legacy
// responses without stay_options — the builder then stages the criteria
// dates as before.
export interface ChosenStay {
  date_from: string;
  date_to: string;
  // Whether this is the search's default block (vs an explicitly picked
  // alternative) — the builder posts a picked block's dates verbatim.
  is_default: boolean;
  priced_date_from: string;
  priced_date_to: string;
  total: string | number | null;
  currency: string | null;
  inclusion: string | null;
}

// One add-unit handed from a result card to the builder (GAP-043): a chosen
// week (absent for legacy results without stay_options — the builder then
// stages the criteria dates) plus, for a banded villa, that week's checked
// occupancy bands.
export interface StayAdd {
  stay?: ChosenStay;
  bands?: OccupancyBand[];
}

// Which dates a chosen stay stages and posts (GAP-007): a real alternative —
// an explicitly picked non-default block, or a default block the search
// rounded to a different length than requested — carries its own dates. A
// default block with the SAME night count is the preferred stay (possibly
// changeover-shifted): the criteria dates are kept so the backend stays the
// single source of the shift and records it. Shared by the builder (staging)
// and the result card (per-week staged markers) so the two can't disagree on
// a week's line identity.
export function stagedStayDates(
  criteria: { date_from: string; date_to: string },
  stay?: { date_from: string; date_to: string; is_default: boolean },
): { date_from: string; date_to: string } {
  // Empty criteria (defensive — a card rendered before any search recorded)
  // fall through to the stay's own dates rather than NaN-poisoning the
  // night-count comparison below.
  const useStayDates =
    stay != null &&
    (!criteria.date_from ||
      !stay.is_default ||
      nightsCount(stay.date_from, stay.date_to) !==
        nightsCount(criteria.date_from, criteria.date_to));
  return useStayDates
    ? { date_from: stay.date_from, date_to: stay.date_to }
    : { date_from: criteria.date_from, date_to: criteria.date_to };
}

// A property that matched the operator's name search but is excluded from the
// priced options because its capacity isn't set (no row, or guests === 0).
// Surfaced as a hint so the operator learns why a known property is missing,
// rather than seeing a bare empty state.
export interface HiddenCapacityProperty {
  id: number;
  name: string;
  slug: string | null;
}

export interface QuoteSearchResult {
  options: QuoteOption[];
  hiddenForCapacity: HiddenCapacityProperty[];
  // Pagination over the strict candidate set (DRF `next`/`count`). The builder
  // pages through candidates via "Load more"; `hiddenForCapacity` is computed
  // once for the whole search (first page only).
  hasMore: boolean;
  totalMatched: number;
}

// One occupancy bracket carried onto a staged line (GAP-044). Fanned out from
// the result's `OccupancyBand` at Add time. `checked` is a shortlist-level
// toggle so the operator can trim bands before save; ≥1 non-POA band must stay
// checked for the line to be valid. `adults` is the representative party the
// backend priced (= max(1, min_party)) and what the expanded saved line posts.
export interface StagedBand {
  min_party: number;
  max_party: number;
  adults: number;
  total: string | number | null;
  currency: string | null;
  is_poa: boolean;
  checked: boolean;
}

// One row in the operator-staged "lines so far" panel. Pre-save shape.
// `is_selected` is intentionally absent — the backend sets it during the
// `accept()` transition (convert-to-booking), not at create time.
// Stable staged-line identity (GAP-043): one villa can be staged at several
// weeks — each week is its OWN line. Sole producer of the `line_id` format;
// `stagedLineProperty` is its only decoder.
export const stagedLineId = (propertyId: number, dateFrom: string): string =>
  `${propertyId}:${dateFrom}`;

export const stagedLineProperty = (lineId: string): number => Number(lineId.split(":", 1)[0]);

export interface StagedLine {
  // `stagedLineId(property_id, date_from)` — everything that updates/removes/
  // expands a line keys on this, never on property_id alone.
  line_id: string;
  property_id: number;
  property_name: string;
  hero_image_url: string | null;
  // The operator's requested stay — what we POST. The backend is the single
  // changeover shifter (GAP-007): it nudges a non-conforming arrival forward
  // on save and records the move on the line, so we send what was requested
  // rather than pre-shifting here.
  date_from: string;
  date_to: string;
  // The dates the engine actually priced — equal to the requested dates unless
  // the arrival was shifted to the changeover day. Displayed in the builder so
  // the shown dates match the shown total; the shift note fires when they
  // differ from the requested dates.
  priced_date_from: string;
  priced_date_to: string;
  adults: number;
  children: number;
  // ISO code the option was priced in (GAP-014) — each result carries its own
  // rate plan's currency. Null when the engine returned no currency (e.g. an
  // unpriceable result); the save path then omits it so the backend defaults
  // canonically.
  currency: string | null;
  // The engine gross for a priced line, or the operator-typed total for a
  // manual line. The shortlist's effective total nets `discount` off this (priced
  // lines only), floored at zero — see `lineEffectiveTotal`.
  total: string | number | null;
  // Per-line edits the shortlist exposes; mirror the fields the backend already
  // supports (GAP-005 #5–#7). Decimal `discount` travels as a string.
  discount: string;
  inclusions: string;
  price_override_reason: string;
  is_manual: boolean;
  // True when the engine couldn't price this villa at all (Q-013 no-rate):
  // there is no engine total to fall back to, so `is_manual` can't be
  // un-ticked — the shortlist disables the checkbox.
  manual_only: boolean;
  notes: string;
  // GAP-044 occupancy fan-out: the occupancy brackets a banded villa was
  // priced into. Bands are ALTERNATIVES, not additive — a banded line carries
  // NO single `total` (it stays null) and contributes nothing to the shortlist
  // subtotal. At save each checked, non-POA band expands to its OWN quotation
  // line (the server re-prices into the bracket); POA bands are display-only.
  occupancy_bands?: StagedBand[];
}

// Line write — what `POST/PATCH /quotations/{id}/lines` accepts.
// Decimal fields (`discount`, `total`) travel as strings to avoid float
// drift through DRF's DecimalField. When `is_manual` is on, the server
// requires `price_override_reason` — we mirror that in Zod for early UX,
// but the server stays the source of truth (its 400 is surfaced inline).
// Decimal fields (`discount`, `total`) travel as strings (e.g. "100.00") so
// they round-trip DRF's DecimalField without float drift. They are optional
// on the wire: omit `total` for a priced (non-manual) line — the server
// prices it — and only send `price_override_reason` for the manual path.
export const quotationLineWriteInputSchema = z
  .object({
    property: z.number().int(),
    date_from: z.string().min(1),
    date_to: z.string().min(1),
    adults: z.number().int().min(1),
    children: z.number().int().min(0),
    // Optional ISO code (GAP-014) — pins the currency the option was priced
    // in; omitted, the backend resolves a canonical default per property.
    currency: z.string().optional(),
    discount: z.string().optional(),
    inclusions: z.string().optional(),
    is_manual: z.boolean(),
    total: z.string().optional(),
    price_override_reason: z.string().optional(),
    notes: z.string(),
  })
  // Mirror the server's manual-reason rule for early UX. The server stays
  // authoritative — its 400 still surfaces inline if this slips through.
  .refine((v) => !v.is_manual || (v.price_override_reason ?? "").trim().length > 0, {
    path: ["price_override_reason"],
    message: i18n.t("quotations:schema_errors.override_reason_required"),
  })
  // Mirror the server's manual-total rule: a manual line needs a non-empty
  // total that parses to a number > 0. Uses the same comma-tolerant parser as
  // the shortlist (`isPositiveMoney`); the server's 400 on `total` still surfaces
  // inline as a belt-and-suspenders if this slips through.
  .refine((v) => !v.is_manual || isPositiveMoney(v.total ?? ""), {
    path: ["total"],
    message: i18n.t("quotations:schema_errors.manual_total_required"),
  });
export type QuotationLineWriteInput = z.infer<typeof quotationLineWriteInputSchema>;

// Header write — what `POST /quotations` accepts. Optional nested `lines`
// (create only) make the builder's save atomic: header + lines + pricing +
// holds succeed or fail as one request, so a mid-save failure can never leave
// a half-populated draft.
export const quotationWriteInputSchema = z.object({
  enquiry: z.number().int().nullable(),
  // GAP-045: `person` is the authoritative customer FK the builder sends (off
  // /contacts). The transitional `guest` write was dropped from this schema in
  // D3-3 and from the backend serializer in D5-2 — `person` is now the sole
  // customer input the backend accepts (a guest-only body is a 400).
  person: z.number().int(),
  agent: z.number().int().nullable().optional(),
  is_unbranded: z.boolean().optional().default(false),
  expires_at: z.string(),
  terms_version: z.number().int(),
  lines: z.array(quotationLineWriteInputSchema).optional(),
});
export type QuotationWriteInput = z.infer<typeof quotationWriteInputSchema>;

// Current terms version — returned by GET /terms-versions/current.
export const termsVersionSchema = z.object({
  id: z.number(),
  version: z.string(),
  is_current: z.boolean(),
  published_at: z.string().nullable().optional(),
});
export type TermsVersion = z.infer<typeof termsVersionSchema>;

// Guest-facing quote preview — returned by GET /quotations/{id}:preview.
// `html` is a self-contained inline-CSS document; the rest are editable
// email defaults the operator can override before sending.
export const quotationPreviewSchema = z.object({
  html: z.string(),
  subject: z.string(),
  intro: z.string(),
  signoff: z.string(),
});
export type QuotationPreview = z.infer<typeof quotationPreviewSchema>;

// Editable email overrides — what the operator submits when sending. Empty
// strings still post; the server treats them as overrides.
export const quotationSendOverridesSchema = z.object({
  subject: z.string(),
  intro: z.string(),
  signoff: z.string(),
});
export type QuotationSendOverrides = z.infer<typeof quotationSendOverridesSchema>;

export const quotationListResponseSchema = paginated(quotationListItemSchema);

// Lines endpoint is a nested router viewset — paginated like everything else.
export const quotationLinesResponseSchema = paginated(quotationLineSchema);

export interface QuotationFilters {
  q?: string;
  status?: string;
  enquiry?: number;
  guest?: number;
  ordering?: string;
  page?: number;
}
