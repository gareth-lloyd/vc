import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import {
  ownerBlockUpdateSchema,
  ownerBlockUpdatesResponseSchema,
  type OwnerBlockUpdate,
  type OwnerBlockUpdateFilters,
} from "./schemas";

function toQuery(filters: OwnerBlockUpdateFilters): QueryParams {
  return {
    seen: filters.seen === undefined ? undefined : String(filters.seen),
    property: filters.property,
  };
}

export async function fetchOwnerBlockUpdates(
  filters: OwnerBlockUpdateFilters = {},
): Promise<Paginated<OwnerBlockUpdate>> {
  const data = await apiGet<unknown>("/owner-block-updates", { query: toQuery(filters) });
  return ownerBlockUpdatesResponseSchema.parse(data);
}

export async function markOwnerBlockUpdateSeen(id: number): Promise<OwnerBlockUpdate> {
  const data = await apiSend<unknown>("POST", `/owner-block-updates/${id}:seen`);
  return ownerBlockUpdateSchema.parse(data);
}

export async function markOwnerBlockUpdateUnseen(id: number): Promise<OwnerBlockUpdate> {
  const data = await apiSend<unknown>("POST", `/owner-block-updates/${id}:unseen`);
  return ownerBlockUpdateSchema.parse(data);
}

export async function contestOwnerBlockUpdate(
  id: number,
  reason: string,
): Promise<OwnerBlockUpdate> {
  const data = await apiSend<unknown>("POST", `/owner-block-updates/${id}:contest`, { reason });
  return ownerBlockUpdateSchema.parse(data);
}
