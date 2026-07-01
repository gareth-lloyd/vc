import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { UserId } from "@/lib/query/keys";
import {
  userDetailSchema,
  userListResponseSchema,
  type UserCreateInput,
  type UserDetail,
  type UserFilters,
  type UserSummary,
  type UserUpdateInput,
} from "./schemas";

function toQuery(filters: UserFilters): QueryParams {
  const roles = filters.role
    ? filters.role
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : undefined;
  return {
    role: roles && roles.length ? roles : undefined,
    is_active: filters.is_active,
    is_staff: filters.is_staff,
    search: filters.search || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchUsers(filters: UserFilters): Promise<Paginated<UserSummary>> {
  const data = await apiGet<unknown>("/users", { query: toQuery(filters) });
  return userListResponseSchema.parse(data);
}

export async function fetchUser(id: UserId): Promise<UserDetail> {
  const data = await apiGet<unknown>(`/users/${id}`);
  return userDetailSchema.parse(data);
}

export async function createUser(body: UserCreateInput): Promise<UserDetail> {
  const data = await apiSend<unknown>("POST", "/users", body);
  return userDetailSchema.parse(data);
}

export async function updateUser(id: UserId, body: Partial<UserUpdateInput>): Promise<UserDetail> {
  const data = await apiSend<unknown>("PATCH", `/users/${id}`, body);
  return userDetailSchema.parse(data);
}

export async function deactivateUser(id: UserId): Promise<void> {
  await apiSend<void>("DELETE", `/users/${id}`);
}

export async function activateUser(id: UserId): Promise<UserDetail> {
  const data = await apiSend<unknown>("POST", `/users/${id}:activate`);
  return userDetailSchema.parse(data);
}

export async function reset2fa(id: UserId): Promise<void> {
  await apiSend<unknown>("POST", `/users/${id}:reset-2fa`);
}
