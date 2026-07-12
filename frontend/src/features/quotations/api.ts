import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { QuotationId } from "@/lib/query/keys";
import { isCapacityUnset, propertyListResponseSchema } from "@/features/properties/schemas";
import { bookingDetailSchema, type BookingDetail } from "@/features/bookings/schemas";
import {
  quotationDetailSchema,
  quotationLineSchema,
  quotationLinesResponseSchema,
  quotationListResponseSchema,
  quotationPreviewSchema,
  quoteOptionSchema,
  stayRepriceSchema,
  termsVersionSchema,
  type QuotationDetail,
  type QuotationFilters,
  type QuotationLine,
  type QuotationLineWriteInput,
  type QuotationListItem,
  type QuotationPreview,
  type QuotationSendOverrides,
  type QuotationWriteInput,
  type QuoteCriteriaInput,
  type QuoteSearchResult,
  type HiddenCapacityProperty,
  type StayReprice,
  type TermsVersion,
} from "./schemas";

function toQuery(filters: QuotationFilters): QueryParams {
  return {
    q: filters.q || undefined,
    status: filters.status || undefined,
    enquiry: filters.enquiry,
    guest: filters.guest,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchQuotations(
  filters: QuotationFilters,
): Promise<Paginated<QuotationListItem>> {
  const data = await apiGet<unknown>("/quotations", { query: toQuery(filters) });
  return quotationListResponseSchema.parse(data);
}

// The query that scopes the status counts: every filter EXCEPT the ones that
// don't change the totals (status/page/ordering). Exported so the hook keys on
// this stripped shape — keying on the full filters refetches identical counts
// on every chip click, page, or sort.
export function quotationStatusCountsQuery(filters: QuotationFilters): QueryParams {
  const query = toQuery(filters);
  delete query.status;
  delete query.page;
  delete query.ordering;
  return query;
}

export async function fetchQuotation(id: QuotationId): Promise<QuotationDetail> {
  const data = await apiGet<unknown>(`/quotations/${id}`);
  return quotationDetailSchema.parse(data);
}

export async function fetchQuotationLines(id: QuotationId): Promise<Paginated<QuotationLine>> {
  const data = await apiGet<unknown>(`/quotations/${id}/lines`);
  return quotationLinesResponseSchema.parse(data);
}

interface PropertyCandidate {
  id: number;
  name: string;
  // The row's internal `name` — distinct villas can share a display name, so
  // the results card uses this (plus capacity) to tell them apart.
  internalName: string;
  bedrooms: number | null;
  sleeps: number | null;
  slug: string | null | undefined;
  // Per-row availability for the searched dates (`available_for_range` on the
  // list row); null when the candidate query carried no date range.
  datesAvailable: boolean | null;
}

interface SearchOptionsResponse {
  quotes: Array<{
    property_id: number;
    available?: boolean;
    error_code?: string;
    error_detail?: string;
    total?: string;
    // Q-018 rate reductions: the pre-reduction total (spread through from the
    // quote breakdown) when the engine quoted reduced prices.
    total_before_reduction?: string | null;
    rate_subtotal?: string;
    currency_code?: string;
    hero_image_url?: string | null;
    date_from?: string;
    date_to?: string;
    inclusion?: string;
    occupancy_pricing?: boolean;
    changeover_day?: string | null;
    min_nights?: number | null;
    max_nights?: number | null;
    is_projected?: boolean;
    stay_options?: Array<{
      date_from: string;
      date_to: string;
      nights: number;
      is_default: boolean;
      is_available: boolean;
    }>;
    occupancy_bands?: Array<{
      min_party: number;
      max_party: number;
      adults: number;
      total?: string | null;
      total_before_reduction?: string | null;
      currency_code?: string | null;
      is_projected?: boolean;
      is_poa?: boolean;
      error_code?: string | null;
    }>;
    lines?: unknown;
    [key: string]: unknown;
  }>;
}

interface PropertySearchFilters {
  country?: string;
  region?: string;
  min_bedrooms?: number;
  max_bedrooms?: number;
  min_guests?: number;
  q?: string;
  // Searched stay window. Sent with `include_unavailable=true` so held/booked
  // villas come back flagged (`available_for_range`) instead of being dropped —
  // the builder shows them as unavailable rather than silently offering them.
  date_from?: string;
  date_to?: string;
}

// Customer-facing name: prefer the display name, fall back to the slug-ish name.
function propertyDisplayName(row: { display_name?: string | null; name: string }): string {
  return row.display_name?.trim() ? row.display_name : row.name;
}

interface CandidatePage {
  candidates: PropertyCandidate[];
  // `next != null` on the DRF envelope — there are more candidates to price.
  hasMore: boolean;
  // Total candidates matching the criteria across all pages (DRF `count`).
  totalMatched: number;
}

async function fetchCandidateProperties(
  filters: PropertySearchFilters,
  page: number,
): Promise<CandidatePage> {
  // Active properties only — pricing engine will reject archived/draft anyway.
  const query: QueryParams = {
    status: "active",
    country: filters.country || undefined,
    region: filters.region || undefined,
    min_bedrooms: filters.min_bedrooms,
    max_bedrooms: filters.max_bedrooms,
    min_guests: filters.min_guests,
    q: filters.q || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    // Keep held/booked villas in the page — each row carries
    // `available_for_range` so the builder can badge them instead.
    include_unavailable: filters.date_from && filters.date_to ? "true" : undefined,
    // Omit page=1 so the first request stays clean (mirrors `toQuery`).
    page: page > 1 ? page : undefined,
  };
  const data = await apiGet<unknown>("/properties", { query });
  const result = propertyListResponseSchema.parse(data);
  return {
    candidates: result.results.map((row) => ({
      id: row.id,
      name: propertyDisplayName(row),
      internalName: row.name,
      bedrooms: row.capacity?.bedrooms ?? null,
      sleeps: row.capacity?.guests ?? null,
      slug: row.slug ?? null,
      datesAvailable: row.available_for_range ?? null,
    })),
    hasMore: result.next != null,
    totalMatched: result.count,
  };
}

async function fetchCapacityUnsetCandidates(
  filters: PropertySearchFilters,
): Promise<HiddenCapacityProperty[]> {
  // Lenient name search: same scope as the strict candidate query but WITHOUT
  // the capacity-derived guards (`min_guests` / `min_bedrooms`). A property that
  // matches by name yet is absent from the strict set *because its capacity
  // isn't set* is the hint we want to surface (see `isCapacityUnset`).
  const query: QueryParams = {
    status: "active",
    country: filters.country || undefined,
    region: filters.region || undefined,
    q: filters.q || undefined,
  };
  const data = await apiGet<unknown>("/properties", { query });
  const page = propertyListResponseSchema.parse(data);
  return page.results
    .filter((row) => isCapacityUnset(row.capacity))
    .map((row) => ({
      id: row.id,
      name: propertyDisplayName(row),
      slug: row.slug ?? null,
    }));
}

export async function searchQuoteOptions(
  criteria: QuoteCriteriaInput,
  page = 1,
): Promise<QuoteSearchResult> {
  const searchFilters: PropertySearchFilters = {
    country: criteria.country || undefined,
    region: criteria.region || undefined,
    q: criteria.q || undefined,
  };
  const datedFilters: PropertySearchFilters = {
    ...searchFilters,
    date_from: criteria.date_from,
    date_to: criteria.date_to,
  };
  // The strict (paged) candidate query and the lenient capacity-hint query are
  // independent requests, so run them concurrently. The hint is best-effort:
  // its failure must never sink the priced-results path, so swallow its error.
  // It describes the whole search (not a page) and is unpaged, so only compute
  // it for the first page — and only for a name search.
  const [candidatePage, capacityUnset] = await Promise.all([
    fetchCandidateProperties(
      {
        ...datedFilters,
        min_bedrooms: criteria.min_bedrooms ?? undefined,
        max_bedrooms: criteria.max_bedrooms ?? undefined,
        min_guests: criteria.adults + criteria.children,
      },
      page,
    ),
    page === 1 && criteria.q
      ? fetchCapacityUnsetCandidates(searchFilters).catch(() => [])
      : Promise.resolve([]),
  ]);
  const { candidates, hasMore, totalMatched } = candidatePage;

  // A property that priced (so it's a strict candidate) isn't "hidden".
  const candidateIds = new Set(candidates.map((c) => c.id));
  const hiddenForCapacity = capacityUnset.filter((p) => !candidateIds.has(p.id));

  if (candidates.length === 0) return { options: [], hiddenForCapacity, hasMore, totalMatched };

  // No `currency` on the request (GAP-014): each property is priced in its
  // own rate plan's currency, reported back per result as `currency_code`.
  // Dates are the client's PREFERRED stay — the backend widens the search
  // window by `flex_days` itself and reports the offerable blocks back as
  // `stay_options`.
  const body = {
    flex_days: criteria.flex_days,
    requests: candidates.map((p) => ({
      property_id: p.id,
      date_from: criteria.date_from,
      date_to: criteria.date_to,
      adults: criteria.adults,
      children: criteria.children,
    })),
  };
  const bulk = await apiSend<SearchOptionsResponse>("POST", "/quotations:search-options", body);
  const byId = new Map(candidates.map((p) => [p.id, p]));

  const options = bulk.quotes.map((q) => {
    const property = byId.get(q.property_id);
    // A date conflict on the candidate row (requested dates held/booked)
    // trumps a priced result, so a held villa can never present as addable —
    // UNLESS the backend offered at least one available stay block: the
    // per-block flags are more precise than the requested-range flag, and an
    // alternate block is exactly what the flexibility window is for.
    const datesUnavailable =
      property?.datesAvailable === false && !q.stay_options?.some((o) => o.is_available);
    return quoteOptionSchema.parse({
      property_id: q.property_id,
      property_name: property?.name ?? `Property #${q.property_id}`,
      internal_name: property?.internalName ?? null,
      bedrooms: property?.bedrooms ?? null,
      sleeps: property?.sleeps ?? null,
      property_slug: property?.slug ?? null,
      hero_image_url: q.hero_image_url ?? null,
      available: !datesUnavailable && q.available !== false && !q.error_code,
      total: q.total ?? null,
      // Q-018: pre-reduction total — powers the "reduced from" hint on the
      // default-week row and the single-total block.
      total_before_reduction: q.total_before_reduction ?? null,
      currency: q.currency_code ?? null,
      rate_subtotal: q.rate_subtotal ?? null,
      date_from: q.date_from ?? null,
      date_to: q.date_to ?? null,
      error_code: datesUnavailable ? "dates_unavailable" : (q.error_code ?? null),
      error_detail: datesUnavailable ? null : (q.error_detail ?? null),
      inclusion: q.inclusion ?? null,
      occupancy_pricing: q.occupancy_pricing ?? null,
      changeover_day: q.changeover_day ?? null,
      min_nights: q.min_nights ?? null,
      max_nights: q.max_nights ?? null,
      is_projected: q.is_projected ?? null,
      stay_options: q.stay_options ?? null,
      occupancy_bands: q.occupancy_bands ?? null,
      breakdown: q,
    });
  });
  return { options, hiddenForCapacity, hasMore, totalMatched };
}

export interface StayRepriceInput {
  property_id: number;
  date_from: string;
  date_to: string;
  adults: number;
  children: number;
}

// Reprice one chosen stay block: same endpoint, one request, no flexibility —
// the block dates are already changeover-aligned, so the backend prices them
// directly. One code path with the search keeps the two from drifting.
export async function repriceStayOption(input: StayRepriceInput): Promise<StayReprice> {
  const data = await apiSend<{ quotes: unknown[] }>("POST", "/quotations:search-options", {
    flex_days: 0,
    requests: [input],
  });
  return stayRepriceSchema.parse(data.quotes[0]);
}

export async function createQuotation(body: QuotationWriteInput): Promise<QuotationDetail> {
  const data = await apiSend<unknown>("POST", "/quotations", body);
  return quotationDetailSchema.parse(data);
}

export async function updateQuotationLine(
  quotationId: QuotationId,
  lineId: number,
  body: Partial<QuotationLineWriteInput>,
): Promise<QuotationLine> {
  const data = await apiSend<unknown>("PATCH", `/quotations/${quotationId}/lines/${lineId}`, body);
  return quotationLineSchema.parse(data);
}

export async function deleteQuotationLine(quotationId: QuotationId, lineId: number): Promise<void> {
  await apiSend<void>("DELETE", `/quotations/${quotationId}/lines/${lineId}`);
}

// Manual availability holds — a deliberate operator action per line; the
// backend 409s (hold_unavailable) when another live hold owns the dates.
export async function holdQuotationLine(
  quotationId: QuotationId,
  lineId: number,
): Promise<QuotationLine> {
  const data = await apiSend<unknown>("POST", `/quotations/${quotationId}/lines/${lineId}:hold`);
  return quotationLineSchema.parse(data);
}

export async function releaseQuotationLineHold(
  quotationId: QuotationId,
  lineId: number,
): Promise<QuotationLine> {
  const data = await apiSend<unknown>(
    "POST",
    `/quotations/${quotationId}/lines/${lineId}:release-hold`,
  );
  return quotationLineSchema.parse(data);
}

// Optional overrides (subject/intro/signoff) flow through as query params so
// the returned html + fields reflect the operator's edits. Passing nothing
// keeps the server's default render.
export async function fetchQuotationPreview(
  id: QuotationId,
  overrides?: Partial<QuotationSendOverrides>,
): Promise<QuotationPreview> {
  const query: QueryParams | undefined = overrides
    ? {
        subject: overrides.subject,
        intro: overrides.intro,
        signoff: overrides.signoff,
      }
    : undefined;
  const data = await apiGet<unknown>(`/quotations/${id}:preview`, { query });
  return quotationPreviewSchema.parse(data);
}

// Optional overrides flow into the guest email; passing nothing keeps the
// server's stored defaults (back-compat for the bare-confirm callers).
export async function sendQuotation(
  id: QuotationId,
  overrides?: QuotationSendOverrides,
): Promise<QuotationDetail> {
  const data = await apiSend<unknown>("POST", `/quotations/${id}:send`, overrides);
  return quotationDetailSchema.parse(data);
}

// Path B (Outlook): records the SENT state without dispatching an email —
// used after the operator copies the quote HTML to the clipboard.
export async function markQuotationManuallySent(id: QuotationId): Promise<QuotationDetail> {
  const data = await apiSend<unknown>("POST", `/quotations/${id}:mark-manually-sent`);
  return quotationDetailSchema.parse(data);
}

export async function duplicateQuotation(id: QuotationId): Promise<QuotationDetail> {
  const data = await apiSend<unknown>("POST", `/quotations/${id}:duplicate`);
  return quotationDetailSchema.parse(data);
}

export async function withdrawQuotation(id: QuotationId, reason: string): Promise<QuotationDetail> {
  const data = await apiSend<unknown>("POST", `/quotations/${id}:withdraw`, { reason });
  return quotationDetailSchema.parse(data);
}

export interface ConvertQuotationInput {
  line: number;
  /** Explicit acceptance signal — the API refuses to convert without it and
   *  stamps `terms_accepted_at` server-side (SMELL-006). */
  terms_accepted: true;
  payment_method?: "card" | "bank_transfer";
}

export async function convertQuotation(
  id: QuotationId,
  body: ConvertQuotationInput,
): Promise<BookingDetail> {
  const data = await apiSend<unknown>("POST", `/quotations/${id}:convert`, body);
  return bookingDetailSchema.parse(data);
}

export async function fetchCurrentTermsVersion(): Promise<TermsVersion> {
  const data = await apiGet<unknown>("/terms-versions/current");
  return termsVersionSchema.parse(data);
}
