import { apiGet, apiSend } from "@/lib/api/client";
import {
  loginResponseSchema,
  permissionsResponseSchema,
  tfaVerifyResponseSchema,
  userMeSchema,
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

export async function verifyTfa(input: TfaVerifyInput): Promise<UserMe> {
  const data = await apiSend<unknown>("POST", "/auth/2fa:verify", input);
  return tfaVerifyResponseSchema.parse(data).user;
}
