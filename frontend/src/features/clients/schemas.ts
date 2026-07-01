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
  // Agent-capacity (GAP-053): the person belongs to an agency or deals through a
  // travel agent — not merely a deal-channel flag.
  is_agent: z.boolean(),
  // GAP-053 chip active-state: the derived >=1-booking flag and the stored client
  // tag set (VIP/Trade). Default so a row missing them still parses.
  is_repeat_customer: z.boolean().default(false),
  tags: z.array(z.string()).default([]),
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
  // Agent-capacity partition: "direct" | "agent" (maps to the backend
  // `client_agent_capacity_expression`).
  capacity?: string;
  // GAP-053 chips: `tags` is a comma-separated ANY-of overlap (e.g. "vip,trade");
  // `repeat` keys on the >=1-booking flag.
  tags?: string;
  repeat?: boolean;
  ordering?: string;
  page?: number;
}
