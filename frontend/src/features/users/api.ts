import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import { userListResponseSchema, type UserFilters, type UserSummary } from "./schemas";

function toQuery(filters: UserFilters): QueryParams {
  // `role` is comma-separated for caller convenience; convert to repeated
  // `?role=` params to match django-filter's `exact` lookup.
  const roles = filters.role
    ? filters.role
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : undefined;
  return {
    role: roles && roles.length ? roles : undefined,
    is_active: filters.is_active,
    search: filters.search || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchUsers(filters: UserFilters): Promise<Paginated<UserSummary>> {
  const data = await apiGet<unknown>("/users", { query: toQuery(filters) });
  return userListResponseSchema.parse(data);
}
