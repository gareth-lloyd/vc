import { z } from "zod";

export const loginInputSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
  remember: z.boolean().optional(),
});
export type LoginInput = z.infer<typeof loginInputSchema>;

export const userMeSchema = z.object({
  id: z.union([z.number(), z.string()]),
  email: z.string(),
  first_name: z.string(),
  last_name: z.string(),
  phone: z.string().nullable().optional(),
  role: z.string().nullable().optional(),
  is_active: z.boolean(),
  is_staff: z.boolean(),
  is_superuser: z.boolean(),
  tfa_method: z.string().nullable().optional(),
  tfa_enrolled_at: z.string().nullable().optional(),
  last_login: z.string().nullable().optional(),
});
export type UserMe = z.infer<typeof userMeSchema>;

export const loginResponseSchema = z.union([
  z.object({
    tfa_required: z.literal(false),
    user: userMeSchema,
  }),
  z.object({
    tfa_required: z.literal(true),
    challenge_token: z.string(),
    expires_in_seconds: z.number(),
  }),
]);
export type LoginResponse = z.infer<typeof loginResponseSchema>;

export const tfaVerifyInputSchema = z.object({
  challenge_token: z.string(),
  code: z.string().min(4).max(10),
});
export type TfaVerifyInput = z.infer<typeof tfaVerifyInputSchema>;

export const tfaVerifyResponseSchema = z.object({
  user: userMeSchema,
});

export const permissionsResponseSchema = z.object({
  role: z.string().nullable(),
  is_superuser: z.boolean(),
  permissions: z.array(z.string()),
});
export type PermissionsResponse = z.infer<typeof permissionsResponseSchema>;
