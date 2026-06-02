import { z } from "zod";
import i18n from "@/i18n";
import { SERVICE_KEYS, TIERS, type ServiceKey } from "@/styles/tokens";
import { SERVICE_STATUSES, type ServiceStatus } from "@/components/data/ServiceDot";

export const serviceKeySchema = z.enum(SERVICE_KEYS);
export const serviceStatusSchema = z.enum(SERVICE_STATUSES);
export const conciergeTierSchema = z.enum(TIERS);

/** One booking's row in the cross-booking coverage matrix. */
export const conciergeOverviewRowSchema = z.object({
  id: z.number(),
  reference: z.string(),
  status: z.string(),
  guest_name: z.string().nullable(),
  property_name: z.string().nullable(),
  region: z.string().nullable(),
  date_from: z.string(),
  arrival_in_days: z.number(),
  // Backend sends every service column, but tolerate a subset: absent cells
  // read as `not_started` at the call site (z.record over an enum key is
  // exhaustive in zod v4, which would reject a partial map).
  services: z.partialRecord(serviceKeySchema, serviceStatusSchema),
  progress: z.number(),
  manager: z.string().nullable(),
  tier: conciergeTierSchema.nullable(),
});

export type ConciergeOverviewRow = z.infer<typeof conciergeOverviewRowSchema>;

export const conciergeOverviewResponseSchema = z.array(conciergeOverviewRowSchema);

/** The single coverage cell returned by the set-status write. */
export const coverageCellSchema = z.object({
  id: z.number(),
  booking: z.number(),
  service: serviceKeySchema,
  status: serviceStatusSchema,
  notes: z.string(),
});

export type CoverageCell = z.infer<typeof coverageCellSchema>;

// Typed-enum dynamic-key lookups (the sanctioned dynamic-key i18n pattern).
export function serviceLabel(service: ServiceKey): string {
  return i18n.t(`concierge:services.${service}`);
}

export function serviceStatusLabel(status: ServiceStatus): string {
  return i18n.t(`concierge:statuses.${status}`);
}
