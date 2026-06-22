import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { CompanyId } from "@/lib/query/keys";
import {
  companiesListResponseSchema,
  companySchema,
  type Company,
  type CompanyFilters,
  type CompanyListItem,
  type CompanyWriteInput,
} from "./schemas";
import { paginated } from "@/lib/api/pagination";

// This directory is the agency view onto Organisation — the API layer owns the
// `org_type=agency` scoping for BOTH reads (toQuery/searchCompanies) and writes
// (createCompany injects it), so a single constant is the only place the value
// lives and reads/writes can never drift.
export const AGENCY = "agency";

function toQuery(filters: CompanyFilters): QueryParams {
  return {
    org_type: AGENCY,
    // The backend matches name/email on `search` (DRF SearchFilter default).
    search: filters.search || undefined,
    status: filters.status || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchCompanies(filters: CompanyFilters): Promise<Paginated<CompanyListItem>> {
  const data = await apiGet<unknown>("/organisations", { query: toQuery(filters) });
  return companiesListResponseSchema.parse(data);
}

export async function fetchCompany(id: CompanyId): Promise<Company> {
  const data = await apiGet<unknown>(`/organisations/${id}`);
  return companySchema.parse(data);
}

export async function searchCompanies(
  query: string,
  opts?: { status?: string },
): Promise<Paginated<Company>> {
  const data = await apiGet<unknown>("/organisations", {
    query: {
      org_type: AGENCY,
      search: query,
      ...(opts?.status ? { status: opts.status } : {}),
    },
  });
  return paginated(companySchema).parse(data);
}

export async function createCompany(body: CompanyWriteInput): Promise<Company> {
  // The directory only ever mints agencies, so the API layer stamps org_type —
  // the form never collects it.
  const data = await apiSend<unknown>("POST", "/organisations", { ...body, org_type: AGENCY });
  return companySchema.parse(data);
}

export async function updateCompany(
  companyId: CompanyId,
  body: Partial<CompanyWriteInput>,
): Promise<Company> {
  const data = await apiSend<unknown>("PATCH", `/organisations/${companyId}`, body);
  return companySchema.parse(data);
}

// A 409 `{code:"protected"}` (the org still has linked agents, PROTECT) surfaces
// as an ApiError the caller catches and renders as a toast — mirroring how
// contacts' deleteContact lets the dialog turn the ApiError into toast text.
export async function deleteCompany(companyId: CompanyId): Promise<void> {
  await apiSend<void>("DELETE", `/organisations/${companyId}`);
}
