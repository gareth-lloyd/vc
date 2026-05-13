import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { formatDateTime, formatRelative } from "@/lib/format/date";
import { useAuditLog } from "@/features/audit/hooks";
import type { AuditLogEntry } from "@/features/audit/schemas";
import type { ContactOutletContext } from "../ContactDetailLayout";

const PAGE_SIZE = 20;

function actionLabelKey(diffs: Record<string, unknown>): string {
  if (!diffs || typeof diffs !== "object") return "labels.default";
  if ("__created__" in diffs) return "labels.create";
  if ("__deleted__" in diffs) return "labels.delete";
  if ("status" in diffs) {
    const transition = diffs.status;
    if (
      transition &&
      typeof transition === "object" &&
      "to" in (transition as Record<string, unknown>)
    ) {
      const to = (transition as Record<string, unknown>).to;
      if (to === "archived") return "labels.archive";
      if (to === "active") return "labels.restore";
    }
  }
  return "labels.update";
}

function AuditEntryRow({ entry }: { entry: AuditLogEntry }) {
  const { t } = useTranslation("audit");
  const [expanded, setExpanded] = useState(false);
  const diffs = entry.field_diffs ?? {};
  const hasDiffs = Object.keys(diffs).length > 0;
  const actorName = entry.actor_email ?? t("entry.system_actor");

  return (
    <li className="px-4 py-3 text-sm">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-foreground font-medium">{t(actionLabelKey(diffs))}</span>
        <span className="text-muted-foreground text-xs" title={formatDateTime(entry.created_at)}>
          {formatRelative(entry.created_at)}
        </span>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{t("entry.by", { actor: actorName })}</p>
      {hasDiffs ? (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-muted-foreground hover:text-foreground text-xs underline"
          >
            {expanded ? t("entry.hide_changes") : t("entry.show_changes")}
          </button>
          {expanded ? (
            <pre className="bg-muted/30 text-muted-foreground mt-2 overflow-x-auto rounded p-2 text-xs">
              {JSON.stringify(diffs, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : (
        <p className="text-muted-foreground mt-1 text-xs italic">{t("entry.no_changes")}</p>
      )}
    </li>
  );
}

export function AuditTab() {
  const { t } = useTranslation("audit");
  const { contact } = useOutletContext<ContactOutletContext>();
  const [page, setPage] = useState(1);

  const query = useAuditLog({
    entity_type: "accounts.contact",
    entity_id: contact.id,
    page,
  });

  if (query.isLoading) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (query.isError) {
    const is403 = query.error instanceof ApiError && query.error.status === 403;
    if (is403) {
      return (
        <div className="p-6">
          <EmptyState
            title={t("errors.permission_denied_title")}
            description={t("errors.permission_denied_description")}
          />
        </div>
      );
    }
    return (
      <div className="p-6">
        <ErrorState title={t("errors.load_failed")} onRetry={() => query.refetch()} />
      </div>
    );
  }

  const entries = query.data?.results ?? [];
  const total = query.data?.count ?? 0;
  const hasNext = query.data?.next != null;
  const hasPrevious = query.data?.previous != null || page > 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (entries.length === 0) {
    return (
      <div className="p-6">
        <EmptyState title={t("empty.title")} description={t("empty.description")} />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6">
      <ol className="border-border bg-card divide-border divide-y rounded-lg border">
        {entries.map((entry) => (
          <AuditEntryRow key={entry.id} entry={entry} />
        ))}
      </ol>
      {totalPages > 1 || hasNext || hasPrevious ? (
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
