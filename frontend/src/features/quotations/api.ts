import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { QuotationId } from "@/lib/query/keys";
import {
  quotationDetailSchema,
  quotationLinesResponseSchema,
  quotationListResponseSchema,
  type QuotationDetail,
  type QuotationFilters,
  type QuotationLine,
  type QuotationListItem,
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
