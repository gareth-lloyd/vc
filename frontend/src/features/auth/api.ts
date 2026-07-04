import { apiGet, apiSend } from "@/lib/api/client";
import {
  enrollConfirmResponseSchema,
  enrollStartResponseSchema,
  loginResponseSchema,
  permissionsResponseSchema,
  tfaVerifyResponseSchema,
  userMeSchema,
  type EnrollConfirmResponse,
  type EnrollStartResponse,
  type LoginInput,
  type LoginResponse,
  type PermissionsResponse,
  type TfaVerifyInput,
  type UserMe,
} from "./schemas";

export async function fetchMe(): Promise<UserMe> {
  const data = await apiGet<unknown>("/auth/me");
  return userMeSchema.parse(data);
}

export async function updateMe(
  input: Partial<Pick<UserMe, "preferred_language">>,
): Promise<UserMe> {
  const data = await apiSend<unknown>("PATCH", "/auth/me", input);
  return userMeSchema.parse(data);
}

export async function fetchPermissions(): Promise<PermissionsResponse> {
  const data = await apiGet<unknown>("/auth/permissions");
  return permissionsResponseSchema.parse(data);
}

export async function login(input: LoginInput): Promise<LoginResponse> {
  const data = await apiSend<unknown>("POST", "/auth/login", {
    email: input.email,
    password: input.password,
  });
  return loginResponseSchema.parse(data);
}

export async function logout(): Promise<void> {
  await apiSend("POST", "/auth/logout");
}

export async function requestPasswordReset(email: string): Promise<void> {
  // 204, no body — the endpoint is silent on whether the email is registered.
  await apiSend("POST", "/auth/password-reset:request", { email });
}

export async function confirmPasswordReset(input: {
  token: string;
  new_password: string;
}): Promise<void> {
  // 204 on success; token failures surface as ApiError (400) for the caller.
  await apiSend("POST", "/auth/password-reset:confirm", input);
}

export async function verifyTfa(input: TfaVerifyInput): Promise<UserMe> {
  const data = await apiSend<unknown>("POST", "/auth/2fa:verify", input);
  return tfaVerifyResponseSchema.parse(data).user;
}

export async function startTfaEnrollment(): Promise<EnrollStartResponse> {
  const data = await apiSend<unknown>("POST", "/auth/2fa:enroll", {});
  return enrollStartResponseSchema.parse(data);
}

export async function confirmTfaEnrollment(code: string): Promise<EnrollConfirmResponse> {
  const data = await apiSend<unknown>("POST", "/auth/2fa:enroll", { code });
  return enrollConfirmResponseSchema.parse(data);
}
