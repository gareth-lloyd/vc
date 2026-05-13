import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const auditLogEntrySchema = z.object({
  id: z.string(),
  entity_type: z.string(),
  object_id: z.string(),
  actor: z.number().nullable().optional(),
  actor_email: z.string().nullable().optional(),
  field_diffs: z.record(z.string(), z.unknown()).optional().default({}),
  correlation_id: z.string().nullable().optional(),
  created_at: z.string(),
});
export type AuditLogEntry = z.infer<typeof auditLogEntrySchema>;

export const auditLogListResponseSchema = paginated(auditLogEntrySchema);

export const auditLogFiltersSchema = z.object({
  entity_type: z.string().optional(),
  entity_id: z.union([z.string(), z.number()]).optional(),
  actor: z.union([z.string(), z.number()]).optional(),
  action: z.string().optional(),
  created_after: z.string().optional(),
  created_before: z.string().optional(),
  page: z.number().optional(),
});
export type AuditLogFilters = z.infer<typeof auditLogFiltersSchema>;
