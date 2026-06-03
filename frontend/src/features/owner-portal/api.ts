import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { BookingId, PropertyId } from "@/lib/query/keys";
import {
  blockRequestWriteInputSchema,
  ownerBlockRequestSchema,
  ownerBlockRequestsResponseSchema,
  ownerBookingDetailSchema,
  ownerBookingsResponseSchema,
  ownerCalendarSchema,
  ownerDashboardSchema,
  ownerMeSchema,
  ownerPropertiesResponseSchema,
  ownerPropertySchema,
  type BlockRequestWriteInput,
  type OwnerBlockRequest,
  type OwnerBlockRequestFilters,
  type OwnerBookingDetail,
  type OwnerBookingFilters,
  type OwnerBookingListItem,
  type OwnerCalendar,
  type OwnerDashboard,
  type OwnerMe,
  type OwnerProperty,
} from "./schemas";

export async function fetchOwnerMe(): Promise<OwnerMe> {
  const data = await apiGet<unknown>("/owner/me");
  return ownerMeSchema.parse(data);
}

export async function fetchOwnerDashboard(): Promise<OwnerDashboard> {
  const data = await apiGet<unknown>("/owner/dashboard");
  return ownerDashboardSchema.parse(data);
}

export async function fetchOwnerProperties(): Promise<Paginated<OwnerProperty>> {
  const data = await apiGet<unknown>("/owner/properties");
  return ownerPropertiesResponseSchema.parse(data);
}

export async function fetchOwnerProperty(id: PropertyId): Promise<OwnerProperty> {
  const data = await apiGet<unknown>(`/owner/properties/${id}`);
  return ownerPropertySchema.parse(data);
}

export async function fetchOwnerPropertyCalendar(
  id: PropertyId,
  from: string,
  to: string,
): Promise<OwnerCalendar> {
  const data = await apiGet<unknown>(`/owner/properties/${id}/calendar`, { query: { from, to } });
  return ownerCalendarSchema.parse(data);
}

function toBookingQuery(filters: OwnerBookingFilters): QueryParams {
  return {
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchOwnerBookings(
  filters: OwnerBookingFilters,
): Promise<Paginated<OwnerBookingListItem>> {
  const data = await apiGet<unknown>("/owner/bookings", { query: toBookingQuery(filters) });
  return ownerBookingsResponseSchema.parse(data);
}

export async function fetchOwnerBooking(id: BookingId): Promise<OwnerBookingDetail> {
  const data = await apiGet<unknown>(`/owner/bookings/${id}`);
  return ownerBookingDetailSchema.parse(data);
}

export async function approveOwnerBooking(id: BookingId): Promise<OwnerBookingDetail> {
  const data = await apiSend<unknown>("POST", `/owner/bookings/${id}:approve`);
  return ownerBookingDetailSchema.parse(data);
}

export async function declineOwnerBooking(
  id: BookingId,
  reason: string,
): Promise<OwnerBookingDetail> {
  const data = await apiSend<unknown>("POST", `/owner/bookings/${id}:decline`, { reason });
  return ownerBookingDetailSchema.parse(data);
}

function toBlockRequestQuery(filters: OwnerBlockRequestFilters): QueryParams {
  return { property: filters.property, status: filters.status };
}

export async function fetchOwnerBlockRequests(
  filters: OwnerBlockRequestFilters = {},
): Promise<OwnerBlockRequest[]> {
  const data = await apiGet<unknown>("/owner/block-requests", {
    query: toBlockRequestQuery(filters),
  });
  return ownerBlockRequestsResponseSchema.parse(data);
}

export async function createOwnerBlockRequest(
  input: BlockRequestWriteInput,
): Promise<OwnerBlockRequest> {
  const body = blockRequestWriteInputSchema.parse(input);
  const data = await apiSend<unknown>("POST", "/owner/block-requests", body);
  return ownerBlockRequestSchema.parse(data);
}

export async function cancelOwnerBlockRequest(id: number): Promise<OwnerBlockRequest> {
  const data = await apiSend<unknown>("POST", `/owner/block-requests/${id}:cancel`);
  return ownerBlockRequestSchema.parse(data);
}
