import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const staffRoleSchema = z.enum(["admin", "reservations", "accounts", "viewer"]);
export type StaffRole = z.infer<typeof staffRoleSchema>;

export const STAFF_ROLES: StaffRole[] = ["admin", "reservations", "accounts", "viewer"];

// Backend's `role` field is a TextChoices on User. Treat as a loose string so
// unexpected values (e.g. legacy nulls, future roles) don't break the picker.
export const userSummarySchema = z.object({
  id: z.number(),
  email: z.string(),
  first_name: z.string().nullable().optional().default(""),
  last_name: z.string().nullable().optional().default(""),
  role: z.string().nullable().optional(),
  is_active: z.boolean(),
  last_login: z.string().nullable().optional(),
  date_joined: z.string().nullable().optional(),
});
export type UserSummary = z.infer<typeof userSummarySchema>;

export const userListResponseSchema = paginated(userSummarySchema);

export const userDetailSchema = z.object({
  id: z.number(),
  email: z.string(),
  first_name: z.string().nullable().optional().default(""),
  last_name: z.string().nullable().optional().default(""),
  phone: z.string().nullable().optional(),
  role: z.string().nullable().optional(),
  is_active: z.boolean(),
  is_staff: z.boolean().optional(),
  is_superuser: z.boolean().optional(),
  tfa_method: z.string().nullable().optional(),
  tfa_enrolled_at: z.string().nullable().optional(),
  last_login: z.string().nullable().optional(),
  date_joined: z.string().nullable().optional(),
});
export type UserDetail = z.infer<typeof userDetailSchema>;

const baseUserFields = z.object({
  email: z.string().email("common:zod.invalid_email").max(254),
  first_name: z.string().trim().max(150).optional(),
  last_name: z.string().trim().max(150).optional(),
  role: staffRoleSchema,
  is_active: z.boolean().optional(),
});

export const userCreateInputSchema = baseUserFields.extend({
  password: z.string().min(8, "auth:errors.password_min").max(128),
});
export type UserCreateInput = z.infer<typeof userCreateInputSchema>;

export const userUpdateInputSchema = baseUserFields.partial({ role: true });
export type UserUpdateInput = z.infer<typeof userUpdateInputSchema>;

export interface UserFilters {
  role?: string;
  is_active?: boolean;
  search?: string;
  page?: number;
  ordering?: string;
}

export function userDisplayName(
  user: Pick<UserSummary, "first_name" | "last_name" | "email">,
): string {
  const name = `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim();
  return name || user.email;
}
