import { z } from "zod";

import i18n from "@/i18n";

// Validation messages are resolved at module load. English-only at launch;
// when a second locale lands, schemas can move to per-validation lookup via
// the global zodErrorMap (path-based routing) or rebuild on language change.
export const loginInputSchema = z.object({
  email: z.string().email({ message: i18n.t("auth:errors.invalid_email") }),
  password: z.string().min(1, { message: i18n.t("auth:errors.password_required") }),
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
  preferred_language: z.string().default("en"),
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

// `POST /auth/2fa:enroll` with no code — starts enrolment.
export const enrollStartResponseSchema = z.object({
  secret: z.string(),
  provisioning_uri: z.string(),
  recovery_codes: z.array(z.string()),
});
export type EnrollStartResponse = z.infer<typeof enrollStartResponseSchema>;

// `POST /auth/2fa:enroll` with a code — confirms enrolment.
export const enrollConfirmResponseSchema = z.object({
  enrolled: z.boolean(),
  tfa_method: z.string(),
});
export type EnrollConfirmResponse = z.infer<typeof enrollConfirmResponseSchema>;

export const enrollConfirmInputSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, { message: "auth:errors.tfa_code_format" }),
});
export type EnrollConfirmInput = z.infer<typeof enrollConfirmInputSchema>;

export const permissionsResponseSchema = z.object({
  role: z.string().nullable(),
  is_superuser: z.boolean(),
  permissions: z.array(z.string()),
});
export type PermissionsResponse = z.infer<typeof permissionsResponseSchema>;
