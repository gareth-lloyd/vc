import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import { clientsListResponseSchema, type ClientFilters, type ClientListItem } from "./schemas";

function toQuery(filters: ClientFilters): QueryParams {
  return {
    search: filters.search || undefined,
    status: filters.status || undefined,
    capacity: filters.capacity || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchClients(filters: ClientFilters): Promise<Paginated<ClientListItem>> {
  const data = await apiGet<unknown>("/clients", { query: toQuery(filters) });
  return clientsListResponseSchema.parse(data);
}
