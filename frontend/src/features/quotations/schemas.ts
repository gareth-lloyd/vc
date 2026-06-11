import { z } from "zod";
import i18n from "@/i18n";
import { paginated } from "@/lib/api/pagination";
import { isPositiveMoney } from "@/lib/format/money";

export const quotationStatusSchema = z.enum(["draft", "sent", "accepted", "expired", "cancelled"]);
export type QuotationStatus = z.infer<typeof quotationStatusSchema>;

// Accepts plain strings because detail/list payloads keep `status` loose
// (the backend's TextChoices may grow); unknown values render verbatim.
export function quotationStatusLabel(status: QuotationStatus | string): string {
  return i18n.t(`quotations:labels.status.${status}`, { defaultValue: status });
}

export const quotationStatusOptions = (): Array<{ value: QuotationStatus; label: string }> =>
  quotationStatusSchema.options.map((value) => ({ value, label: quotationStatusLabel(value) }));

// Statuses that block further transitions (no send, no withdraw).
export const TERMINAL_QUOTATION_STATUSES: readonly QuotationStatus[] = [
  "accepted",
  "cancelled",
  "expired",
] as const;

// `status` is permissive — backend's TextChoices may grow and we don't want
// to crash the list page if a new value shows up.
const looseStatus = z.string();

export const quotationListItemSchema = z.object({
  id: z.number(),
  reference: z.string(),
  enquiry: z.number().nullable().optional(),
  enquiry_reference: z.string().nullable().optional(),
  guest: z.number().nullable().optional(),
  guest_name: z.string().nullable().optional(),
  agent: z.number().nullable().optional(),
  agent_name: z.string().nullable().optional(),
  status: looseStatus,
  expires_at: z.string().nullable().optional(),
  is_unbranded: z.boolean().optional().default(false),
  terms_version: z.number().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type QuotationListItem = z.infer<typeof quotationListItemSchema>;

export const quotationLineSchema = z.object({
  id: z.number(),
  quotation: z.number().optional(),
  property: z.number().nullable().optional(),
  property_name: z.string().nullable().optional(),
  hero_image_url: z.string().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  // The original arrival when the engine nudged it forward to the property's
  // changeover day (GAP-007). Null/absent when the dates weren't moved.
  changeover_shifted_from: z.string().nullable().optional(),
  adults: z.number().optional().default(0),
  children: z.number().optional().default(0),
  // ISO code the line was priced in (GAP-014) — currency lives per line, not
  // on the quotation header; a mixed-currency quote is legacy-parity.
  currency: z.string().nullable().optional(),
  pricing_snapshot: z.unknown().optional(),
  total: z.union([z.string(), z.number()]).nullable().optional(),
  discount: z.union([z.string(), z.number()]).nullable().optional(),
  inclusions: z.string().optional().default(""),
  price_override_reason: z.string().optional().default(""),
  is_selected: z.boolean().optional().default(false),
  is_manual: z.boolean().optional().default(false),
  notes: z.string().optional().default(""),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type QuotationLine = z.infer<typeof quotationLineSchema>;

// ----------------------------------------------------------------------
// Quote builder schemas — criteria, search results, save payload.
// ----------------------------------------------------------------------

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
    // above stay the client's true requested stay.
    flex_days: z.number().int().min(0).max(3),
  })
  .refine((v) => !v.date_from || !v.date_to || v.date_from < v.date_to, {
    path: ["date_to"],
    message: i18n.t("quotations:schema_errors.date_to_after_date_from"),
  });
export type QuoteCriteriaInput = z.infer<typeof quoteCriteriaInputSchema>;

// One offerable stay block for a result — always ≥1 on a priced result; >1
// only when a fixed-changeover property's flexibility window admits several
// changeover-to-changeover blocks. `is_available` is an advisory snapshot
// (the save-time hold is the real guard); only the default block is priced
// up front — picking another fires a reprice.
export const stayOptionSchema = z.object({
  date_from: z.string(),
  date_to: z.string(),
  nights: z.number(),
  is_default: z.boolean(),
  is_available: z.boolean(),
});
export type StayOption = z.infer<typeof stayOptionSchema>;

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
  hero_image_url: z.string().nullable().optional(),
  available: z.boolean(),
  total: z.union([z.string(), z.number()]).nullable().optional(),
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
  breakdown: z.unknown().optional(),
});
export type QuoteOption = z.infer<typeof quoteOptionSchema>;

// What a block reprice returns — the same flattened quote-entry shape, but
// the caller already holds the property context so only the pricing fields
// are parsed. Error entries keep the bulk error_code shape.
export const stayRepriceSchema = z.object({
  available: z.boolean().optional().default(false),
  total: z.union([z.string(), z.number()]).nullable().optional(),
  currency_code: z.string().nullable().optional(),
  date_from: z.string().nullable().optional(),
  date_to: z.string().nullable().optional(),
  // Set when the engine still nudged the arrival (GAP-007) — surfaced inline
  // so the picker never silently shows different dates than were clicked.
  changeover_shifted_from: z.string().nullable().optional(),
  inclusion: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  error_detail: z.string().nullable().optional(),
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

// One row in the operator-staged "lines so far" panel. Pre-save shape.
// `is_selected` is intentionally absent — the backend sets it during the
// `accept()` transition (convert-to-booking), not at create time.
export interface StagedLine {
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
  // manual line. The cart's effective total nets `discount` off this (priced
  // lines only), floored at zero — see `lineEffectiveTotal`.
  total: string | number | null;
  // Per-line edits the cart exposes; mirror the fields the backend already
  // supports (GAP-005 #5–#7). Decimal `discount` travels as a string.
  discount: string;
  inclusions: string;
  price_override_reason: string;
  is_manual: boolean;
  // True when the engine couldn't price this villa at all (Q-013 no-rate):
  // there is no engine total to fall back to, so `is_manual` can't be
  // un-ticked — the cart disables the checkbox.
  manual_only: boolean;
  notes: string;
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
  // the cart (`isPositiveMoney`); the server's 400 on `total` still surfaces
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
  guest: z.number().int(),
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

export const guestSchema = z.object({
  id: z.number(),
  first_name: z.string(),
  last_name: z.string(),
  // Email is optional on the backend now — absence is null, never a synthetic.
  email: z.string().nullable(),
});
export type GuestSummary = z.infer<typeof guestSchema>;

export const quotationDetailSchema = quotationListItemSchema.extend({
  cancel_reason: z.string().optional().default(""),
  lines: z.array(quotationLineSchema).optional().default([]),
});
export type QuotationDetail = z.infer<typeof quotationDetailSchema>;

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
