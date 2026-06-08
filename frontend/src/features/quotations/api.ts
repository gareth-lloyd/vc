import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { QuotationId } from "@/lib/query/keys";
import { propertyListResponseSchema } from "@/features/properties/schemas";
import { bookingDetailSchema, type BookingDetail } from "@/features/bookings/schemas";
import {
  guestSchema,
  quotationDetailSchema,
  quotationLineSchema,
  quotationLinesResponseSchema,
  quotationListResponseSchema,
  quotationPreviewSchema,
  quoteOptionSchema,
  termsVersionSchema,
  type GuestSummary,
  type QuotationDetail,
  type QuotationFilters,
  type QuotationLine,
  type QuotationLineWriteInput,
  type QuotationListItem,
  type QuotationPreview,
  type QuotationSendOverrides,
  type QuotationWriteInput,
  type QuoteCriteriaInput,
  type QuoteOption,
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
  slug: string | null | undefined;
}

interface PricingBulkResponse {
  quotes: Array<{
    property_id: number;
    available?: boolean;
    error_code?: string;
    error_detail?: string;
    total?: string;
    rate_subtotal?: string;
    currency_code?: string;
    hero_image_url?: string | null;
    date_from?: string;
    date_to?: string;
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
}

async function fetchCandidateProperties(
  filters: PropertySearchFilters,
): Promise<PropertyCandidate[]> {
  // Active properties only — pricing engine will reject archived/draft anyway.
  const query: QueryParams = {
    status: "active",
    country: filters.country || undefined,
    region: filters.region || undefined,
    min_bedrooms: filters.min_bedrooms,
    max_bedrooms: filters.max_bedrooms,
    min_guests: filters.min_guests,
    q: filters.q || undefined,
  };
  const data = await apiGet<unknown>("/properties", { query });
  const page = propertyListResponseSchema.parse(data);
  return page.results.map((row) => ({
    id: row.id,
    name: row.display_name?.trim() ? row.display_name : row.name,
    slug: row.slug ?? null,
  }));
}

export async function searchQuoteOptions(
  criteria: QuoteCriteriaInput,
  currency: string,
): Promise<QuoteOption[]> {
  const candidates = await fetchCandidateProperties({
    country: criteria.country || undefined,
    region: criteria.region || undefined,
    min_bedrooms: criteria.min_bedrooms ?? undefined,
    max_bedrooms: criteria.max_bedrooms ?? undefined,
    min_guests: criteria.adults + criteria.children,
    q: criteria.q || undefined,
  });
  if (candidates.length === 0) return [];

  const body = {
    currency,
    requests: candidates.map((p) => ({
      property_id: p.id,
      date_from: criteria.date_from,
      date_to: criteria.date_to,
      adults: criteria.adults,
      children: criteria.children,
    })),
  };
  const bulk = await apiSend<PricingBulkResponse>("POST", "/pricing:quote-bulk", body);
  const byId = new Map(candidates.map((p) => [p.id, p]));

  return bulk.quotes.map((q) => {
    const property = byId.get(q.property_id);
    return quoteOptionSchema.parse({
      property_id: q.property_id,
      property_name: property?.name ?? `Property #${q.property_id}`,
      property_slug: property?.slug ?? null,
      hero_image_url: q.hero_image_url ?? null,
      available: q.available !== false && !q.error_code,
      total: q.total ?? null,
      currency: q.currency_code ?? currency,
      rate_subtotal: q.rate_subtotal ?? null,
      date_from: q.date_from ?? null,
      date_to: q.date_to ?? null,
      error_code: q.error_code ?? null,
      error_detail: q.error_detail ?? null,
      breakdown: q,
    });
  });
}

export async function createQuotation(body: QuotationWriteInput): Promise<QuotationDetail> {
  const data = await apiSend<unknown>("POST", "/quotations", body);
  return quotationDetailSchema.parse(data);
}

export async function createQuotationLine(
  quotationId: QuotationId,
  body: QuotationLineWriteInput,
): Promise<QuotationLine> {
  const data = await apiSend<unknown>("POST", `/quotations/${quotationId}/lines`, body);
  return quotationLineSchema.parse(data);
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

interface GuestWriteInput {
  first_name: string;
  last_name: string;
  // Email optional — a phone-only guest is valid; never fabricate a synthetic.
  email?: string;
  phone?: string;
}

export async function createGuest(body: GuestWriteInput): Promise<GuestSummary> {
  const data = await apiSend<unknown>("POST", "/guests", body);
  return guestSchema.parse(data);
}
