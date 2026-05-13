import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { QuotationId } from "@/lib/query/keys";
import {
  guestSchema,
  quotationDetailSchema,
  quotationLineSchema,
  quotationLinesResponseSchema,
  quotationListResponseSchema,
  quoteOptionSchema,
  termsVersionSchema,
  type GuestSummary,
  type QuotationDetail,
  type QuotationFilters,
  type QuotationLine,
  type QuotationLineWriteInput,
  type QuotationListItem,
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

export async function fetchQuotation(id: QuotationId): Promise<QuotationDetail> {
  const data = await apiGet<unknown>(`/quotations/${id}`);
  return quotationDetailSchema.parse(data);
}

export async function fetchQuotationLines(id: QuotationId): Promise<Paginated<QuotationLine>> {
  const data = await apiGet<unknown>(`/quotations/${id}/lines`);
  return quotationLinesResponseSchema.parse(data);
}

// ----------------------------------------------------------------------
// Quote builder — property search + bulk pricing.
// ----------------------------------------------------------------------

// Lightweight property-summary subset for the builder result cards.
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
  const parsed = (data as { results?: Array<Record<string, unknown>> }).results ?? [];
  return parsed.map((row) => ({
    id: row.id as number,
    name: (row.display_name as string) || (row.name as string),
    slug: (row.slug as string | null | undefined) ?? null,
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
      available: q.available !== false && !q.error_code,
      total: q.total ?? null,
      currency: q.currency_code ?? currency,
      rate_subtotal: q.rate_subtotal ?? null,
      error_code: q.error_code ?? null,
      error_detail: q.error_detail ?? null,
      breakdown: q,
    });
  });
}

// ----------------------------------------------------------------------
// Quote save — header + lines (server re-prices each line).
// ----------------------------------------------------------------------

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

// ----------------------------------------------------------------------
// Supporting lookups.
// ----------------------------------------------------------------------

export async function fetchCurrentTermsVersion(): Promise<TermsVersion> {
  const data = await apiGet<unknown>("/terms-versions/current");
  return termsVersionSchema.parse(data);
}

interface GuestWriteInput {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
}

export async function createGuest(body: GuestWriteInput): Promise<GuestSummary> {
  const data = await apiSend<unknown>("POST", "/guests", body);
  return guestSchema.parse(data);
}
