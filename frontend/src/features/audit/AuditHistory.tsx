import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActivityList } from "@/components/data/ActivityList";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime, formatRelative } from "@/lib/format/date";
import { useAuditLog } from "./hooks";
import { interpretEntry, REDACTED, type DiffRow } from "./diff";
import type { AuditLogEntry } from "./schemas";

/** snake_case backend field name → "Title case" label. The audit surface is an
 * admin-only technical view, so humanised field names beat maintaining a
 * per-model translation table for dozens of columns across every tracked model. */
function humanizeField(field: string): string {
  const cleaned = field.replace(/_/g, " ").trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function DiffValue({ value }: { value: unknown }) {
  const { t } = useTranslation("audit");
  if (value === null || value === undefined || value === "") {
    return <span className="text-muted-foreground">{t("value.empty")}</span>;
  }
  if (value === REDACTED) {
    return <span className="text-muted-foreground italic">{t("value.redacted")}</span>;
  }
  if (typeof value === "boolean") {
    return <span>{value ? t("value.yes") : t("value.no")}</span>;
  }
  if (typeof value === "object") {
    return <span className="font-mono text-xs">{JSON.stringify(value)}</span>;
  }
  return <span>{String(value)}</span>;
}

function DiffRowItem({ row }: { row: DiffRow }) {
  const { t } = useTranslation("audit");
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
      <span className="text-foreground font-medium">{humanizeField(row.field)}</span>
      <span className="text-muted-foreground inline-flex items-center gap-1">
        <DiffValue value={row.before} />
        <span aria-hidden>{t("diff.arrow")}</span>
        <DiffValue value={row.after} />
      </span>
    </div>
  );
}

function AuditEntryRow({ entry }: { entry: AuditLogEntry }) {
  const { t } = useTranslation("audit");
  const { action, rows, mergedInto, rewrites } = interpretEntry(entry.field_diffs ?? {});
  const actorName = entry.actor_email ?? t("entry.system_actor");
  const rewriteCount = rewrites ? Object.values(rewrites).reduce((sum, n) => sum + n, 0) : 0;
  const labelKey =
    action === "deleted" ? "labels.delete" : action === "merged" ? "labels.merge" : "labels.update";

  return (
    <li className="px-4 py-3 text-sm">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-foreground font-medium">{t(labelKey)}</span>
        <span className="text-muted-foreground text-xs" title={formatDateTime(entry.created_at)}>
          {formatRelative(entry.created_at)}
        </span>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{t("entry.by", { actor: actorName })}</p>

      {action === "deleted" || action === "merged" ? (
        <div className="border-destructive/30 bg-destructive/5 text-foreground mt-2 rounded border px-2 py-1 text-xs">
          <p>
            {action === "merged" ? t("banner.merged", { target: mergedInto }) : t("banner.deleted")}
          </p>
          {action === "merged" && rewriteCount > 0 ? (
            <p className="text-muted-foreground">{t("banner.rewrites", { count: rewriteCount })}</p>
          ) : null}
        </div>
      ) : null}

      {rows.length > 0 ? (
        <div className="mt-2 space-y-1">
          {rows.map((row) => (
            <DiffRowItem key={row.field} row={row} />
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground mt-1 text-xs italic">{t("entry.no_changes")}</p>
      )}
    </li>
  );
}

/**
 * Admin-only, single-target audit-trail (field-diff) view for one entity.
 * The backend gates `GET /audit-log` on the admin role, so a non-admin caller
 * gets a 403 here, surfaced as a permission notice rather than an error.
 */
export function AuditHistory({
  entityType,
  entityId,
}: {
  entityType: string;
  entityId: number | string;
}) {
  const { t } = useTranslation("audit");
  // Unique per instance — the property History tab mounts two side by side.
  const baseId = useId();
  const fromId = `${baseId}-from`;
  const toId = `${baseId}-to`;
  const [page, setPage] = useState(1);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  // Reset paging + filters when the target entity changes. The detail route
  // reuses this component across sibling records (e.g. /bookings/:id/history),
  // so without this the previous record's page/filters would leak onto the next.
  const target = `${entityType}:${entityId}`;
  const [prevTarget, setPrevTarget] = useState(target);
  if (target !== prevTarget) {
    setPrevTarget(target);
    setPage(1);
    setFrom("");
    setTo("");
  }

  const query = useAuditLog({
    entity_type: entityType,
    entity_id: entityId,
    page,
    created_after: from || undefined,
    // `created_at__lte` compares the full timestamp, so widen the upper bound to
    // end-of-day to keep the chosen date inclusive.
    created_before: to ? `${to}T23:59:59` : undefined,
  });

  const updateFrom = (value: string) => {
    setFrom(value);
    setPage(1);
  };
  const updateTo = (value: string) => {
    setTo(value);
    setPage(1);
  };
  const clearFilters = () => {
    setFrom("");
    setTo("");
    setPage(1);
  };

  const filterBar = (
    <div className="flex flex-wrap items-end gap-3">
      <div className="space-y-1">
        <Label htmlFor={fromId} className="text-xs">
          {t("filters.from")}
        </Label>
        <Input
          id={fromId}
          type="date"
          value={from}
          onChange={(e) => updateFrom(e.target.value)}
          className="h-8 w-auto"
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor={toId} className="text-xs">
          {t("filters.to")}
        </Label>
        <Input
          id={toId}
          type="date"
          value={to}
          onChange={(e) => updateTo(e.target.value)}
          className="h-8 w-auto"
        />
      </div>
      {from || to ? (
        <Button variant="ghost" size="sm" onClick={clearFilters}>
          {t("filters.clear")}
        </Button>
      ) : null}
    </div>
  );

  if (query.isLoading) {
    return (
      <div className="space-y-3">
        {filterBar}
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const is403 = query.error instanceof ApiError && query.error.status === 403;
    if (is403) {
      return (
        <EmptyState
          title={t("errors.permission_denied_title")}
          description={t("errors.permission_denied_description")}
        />
      );
    }
    return (
      <div className="space-y-4">
        {filterBar}
        <ErrorState title={t("errors.load_failed")} onRetry={() => query.refetch()} />
      </div>
    );
  }

  const entries = query.data?.results ?? [];
  const hasNext = query.data?.next != null;
  // `page` is the authoritative local source for the Previous control — you can
  // always step back from page > 1. (The server's `previous` is redundant here
  // and goes stale if the result set shrinks between loads.)
  const hasPrevious = page > 1;

  return (
    <div className="space-y-4">
      {filterBar}
      {entries.length === 0 ? (
        <EmptyState title={t("empty.title")} description={t("empty.description")} />
      ) : (
        <ActivityList as="ol">
          {entries.map((entry) => (
            <AuditEntryRow key={entry.id} entry={entry} />
          ))}
        </ActivityList>
      )}
      {hasNext || hasPrevious ? (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!hasPrevious}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t("actions.previous_page")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasNext}
            onClick={() => setPage((p) => p + 1)}
          >
            {t("actions.next_page")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
