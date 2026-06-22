import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

// Mirrors accounts.enums.PersonStatus — the directory lists renter Persons.
export const clientStatusSchema = z.enum(["active", "inactive", "anonymized"]);
export type ClientStatus = z.infer<typeof clientStatusSchema>;

export const clientListItemSchema = z.object({
  id: z.number(),
  title: z.string().nullable().optional(),
  first_name: z.string().nullable().optional(),
  last_name: z.string().nullable().optional(),
  primary_email: z.string().nullable().optional(),
  primary_phone: z.string().nullable().optional(),
  // Booking channel: true if any of the client's deals names a travel agent.
  is_agent: z.boolean(),
  // Distinct region slugs the client has been quoted / booked in (GAP-047
  // Unit 2). Default to [] so a row missing them still parses.
  quoted_region_slugs: z.array(z.string()).default([]),
  booked_region_slugs: z.array(z.string()).default([]),
  status: clientStatusSchema,
});
export type ClientListItem = z.infer<typeof clientListItemSchema>;

export const clientsListResponseSchema = paginated(clientListItemSchema);

export interface ClientFilters {
  // The backend's SearchFilter reads `search` (DRF default).
  search?: string;
  status?: string;
  // Booking channel: "direct" | "agent" (maps to the `is_agent` annotation).
  capacity?: string;
  ordering?: string;
  page?: number;
}
