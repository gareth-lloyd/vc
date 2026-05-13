import { z } from "zod";

export const systemSettingsSchema = z.object({
  settings: z.record(z.string(), z.unknown()).optional().default({}),
  updated_at: z.string().nullable().optional(),
});
export type SystemSettings = z.infer<typeof systemSettingsSchema>;

export const systemSettingsWriteInputSchema = z.object({
  settings: z.record(z.string(), z.unknown()),
});
export type SystemSettingsWriteInput = z.infer<typeof systemSettingsWriteInputSchema>;
