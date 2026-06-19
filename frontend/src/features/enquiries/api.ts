import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { EnquiryId } from "@/lib/query/keys";
import type { LeadStatus } from "@/styles/tokens";
import {
  assignEnquiryInputSchema,
  closeEnquiryInputSchema,
  enquiryActivityResponseSchema,
  enquiryDetailSchema,
  enquiryListResponseSchema,
  enquiryNoteSchema,
  enquiryNotesResponseSchema,
  type AssignEnquiryInput,
  type CloseEnquiryInput,
  type EnquiryActivity,
  type EnquiryDetail,
  type EnquiryFilters,
  type EnquiryListItem,
  type EnquiryNote,
  type EnquiryNoteWriteInput,
  type EnquiryWriteInput,
} from "./schemas";

function toQuery(filters: EnquiryFilters): QueryParams {
  return {
    q: filters.q || undefined,
    status: filters.status || undefined,
    site_source: filters.site_source || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchEnquiries(filters: EnquiryFilters): Promise<Paginated<EnquiryListItem>> {
  const data = await apiGet<unknown>("/enquiries", { query: toQuery(filters) });
  return enquiryListResponseSchema.parse(data);
}

// The query that scopes the status counts: every filter EXCEPT the ones that
// don't change the totals (status/page/ordering). Exported so the hook keys on
// this stripped shape — keying on the full filters refetches identical counts
// on every chip click, page, or sort.
export function enquiryStatusCountsQuery(filters: EnquiryFilters): QueryParams {
  const query = toQuery(filters);
  delete query.status;
  delete query.page;
  delete query.ordering;
  return query;
}

export async function fetchEnquiry(id: EnquiryId): Promise<EnquiryDetail> {
  const data = await apiGet<unknown>(`/enquiries/${id}`);
  return enquiryDetailSchema.parse(data);
}

export async function fetchEnquiryActivity(id: EnquiryId): Promise<EnquiryActivity[]> {
  const data = await apiGet<unknown>(`/enquiries/${id}/activity`);
  return enquiryActivityResponseSchema.parse(data);
}

export async function fetchEnquiryNotes(id: EnquiryId): Promise<Paginated<EnquiryNote>> {
  const data = await apiGet<unknown>(`/enquiries/${id}/notes`);
  return enquiryNotesResponseSchema.parse(data);
}

export async function createEnquiryNote(
  enquiryId: EnquiryId,
  body: EnquiryNoteWriteInput,
): Promise<EnquiryNote> {
  const data = await apiSend<unknown>("POST", `/enquiries/${enquiryId}/notes`, body);
  return enquiryNoteSchema.parse(data);
}

export async function createEnquiry(body: EnquiryWriteInput): Promise<EnquiryDetail> {
  const data = await apiSend<unknown>("POST", "/enquiries", body);
  return enquiryDetailSchema.parse(data);
}

export async function updateEnquiry(
  id: EnquiryId,
  body: Partial<EnquiryWriteInput>,
): Promise<EnquiryDetail> {
  const data = await apiSend<unknown>("PATCH", `/enquiries/${id}`, body);
  return enquiryDetailSchema.parse(data);
}

export async function assignEnquiry(
  id: EnquiryId,
  body: AssignEnquiryInput,
): Promise<EnquiryDetail> {
  const parsed = assignEnquiryInputSchema.parse(body);
  const data = await apiSend<unknown>("POST", `/enquiries/${id}:assign`, parsed);
  return enquiryDetailSchema.parse(data);
}

export async function closeEnquiry(id: EnquiryId, body: CloseEnquiryInput): Promise<EnquiryDetail> {
  const parsed = closeEnquiryInputSchema.parse(body);
  const data = await apiSend<unknown>("POST", `/enquiries/${id}:close`, parsed);
  return enquiryDetailSchema.parse(data);
}

export async function setEnquiryLeadStatus(
  id: EnquiryId,
  value: LeadStatus,
): Promise<EnquiryDetail> {
  // Audited action (mirrors :assign) — writes a LEAD_STATUS_CHANGED event +
  // AuditLog. The lead_status field is read-only on the write serializer.
  const data = await apiSend<unknown>("POST", `/enquiries/${id}:set-lead-status`, {
    lead_status: value,
  });
  return enquiryDetailSchema.parse(data);
}

export async function reopenEnquiry(id: EnquiryId, reason: string): Promise<EnquiryDetail> {
  const data = await apiSend<unknown>("POST", `/enquiries/${id}:reopen`, { reason });
  return enquiryDetailSchema.parse(data);
}

// Convert returns 404/400 unless a quotation already exists. The convert
// affordance lives on the quotation detail page (ConvertQuotationDialog), which
// accepts a quotation and flips the parent enquiry to `converted`.
export async function convertEnquiry(id: EnquiryId, quotation: number): Promise<EnquiryDetail> {
  const data = await apiSend<unknown>("POST", `/enquiries/${id}:convert`, { quotation });
  return enquiryDetailSchema.parse(data);
}
