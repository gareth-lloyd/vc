import { apiGet, apiSend } from "@/lib/api/client";
import {
  systemSettingsSchema,
  type SystemSettings,
  type SystemSettingsWriteInput,
} from "./schemas";

export async function fetchSystemSettings(): Promise<SystemSettings> {
  const data = await apiGet<unknown>("/system/settings");
  return systemSettingsSchema.parse(data);
}

export async function updateSystemSettings(
  body: SystemSettingsWriteInput,
): Promise<SystemSettings> {
  const data = await apiSend<unknown>("PATCH", "/system/settings", body);
  return systemSettingsSchema.parse(data);
}
