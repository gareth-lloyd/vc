import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const staffRoleSchema = z.enum(["admin", "reservations", "accounts", "viewer"]);
export type StaffRole = z.infer<typeof staffRoleSchema>;

// Backend's `role` field is a TextChoices on User. Treat as a loose string so
// unexpected values (e.g. legacy nulls, future roles) don't break the picker.
export const userSummarySchema = z.object({
  id: z.number(),
  email: z.string(),
  first_name: z.string().optional().default(""),
  last_name: z.string().optional().default(""),
  role: z.string().nullable().optional(),
  is_active: z.boolean(),
});
export type UserSummary = z.infer<typeof userSummarySchema>;

export const userListResponseSchema = paginated(userSummarySchema);

export interface UserFilters {
  // Comma-separated list, sent through verbatim. Backend uses `?role=reservations`
  // by default; multi-value queries hit the same filter param repeated. We send
  // a single value or join multiple roles client-side.
  role?: string;
  is_active?: boolean;
  search?: string;
  page?: number;
}

export function userDisplayName(user: UserSummary): string {
  const name = `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim();
  return name || user.email;
}
