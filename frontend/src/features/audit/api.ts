import { apiGet } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import { auditLogListResponseSchema, type AuditLogEntry, type AuditLogFilters } from "./schemas";

function toQuery(filters: AuditLogFilters): QueryParams {
  return {
    entity_type: filters.entity_type || undefined,
    entity_id: filters.entity_id != null ? String(filters.entity_id) : undefined,
    actor: filters.actor != null ? String(filters.actor) : undefined,
    action: filters.action || undefined,
    created_after: filters.created_after || undefined,
    created_before: filters.created_before || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchAuditLog(filters: AuditLogFilters): Promise<Paginated<AuditLogEntry>> {
  const data = await apiGet<unknown>("/audit-log", { query: toQuery(filters) });
  return auditLogListResponseSchema.parse(data);
}
