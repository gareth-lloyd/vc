import { z } from "zod";
import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";

/** `{ status: count }` map returned by every `:status-counts` endpoint. */
export const statusCountsSchema = z.record(z.string(), z.number());
export type StatusCounts = z.infer<typeof statusCountsSchema>;

export async function fetchStatusCounts(path: string, query: QueryParams): Promise<StatusCounts> {
  const data = await apiGet<unknown>(path, { query });
  return statusCountsSchema.parse(data);
}
