import { apiGet, apiSend } from "@/lib/api/client";
import type { ServiceKey } from "@/styles/tokens";
import type { ServiceStatus } from "@/components/data/ServiceDot";
import {
  conciergeOverviewResponseSchema,
  coverageCellSchema,
  type ConciergeOverviewRow,
  type CoverageCell,
} from "./schemas";

export async function fetchConciergeOverview(): Promise<ConciergeOverviewRow[]> {
  const data = await apiGet<unknown>("/concierge/overview");
  return conciergeOverviewResponseSchema.parse(data);
}

export interface SetServiceStatusInput {
  bookingId: number;
  service: ServiceKey;
  status: ServiceStatus;
}

export async function setServiceStatus(input: SetServiceStatusInput): Promise<CoverageCell> {
  const data = await apiSend<unknown>(
    "POST",
    `/concierge/${input.bookingId}/coverage/${input.service}:set-status`,
    { status: input.status },
  );
  return coverageCellSchema.parse(data);
}
