import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { ActivityList } from "@/components/data/ActivityList";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { formatDate, formatDateTime } from "@/lib/format/date";
import { ContestDialog } from "./ContestDialog";
import { useMarkSeen, useMarkUnseen, useOwnerBlockUpdates } from "./hooks";
import type { OwnerBlockUpdate, OwnerBlockUpdateFilters } from "./schemas";

export function OwnerBlockUpdatesPage() {
  const { t } = useTranslation("owner");
  const [params, setParams] = useSearchParams();
  const unseenOnly = params.get("seen") === "false";
  const hasRole = useHasReservationsRole();
  const [contestId, setContestId] = useState<number | null>(null);

  const filters: OwnerBlockUpdateFilters = useMemo(
    () => (unseenOnly ? { seen: false } : {}),
    [unseenOnly],
  );

  const query = useOwnerBlockUpdates(filters);
  const markSeen = useMarkSeen();
  const markUnseen = useMarkUnseen();

  const toggleUnseen = (next: boolean) => {
    setParams(
      (prev) => {
        const nextParams = new URLSearchParams(prev);
        if (next) nextParams.set("seen", "false");
        else nextParams.delete("seen");
        return nextParams;
      },
      { replace: true },
    );
  };

  const handleSeenToggle = async (update: OwnerBlockUpdate) => {
    try {
      if (update.is_seen) await markUnseen.mutateAsync(update.id);
      else await markSeen.mutateAsync(update.id);
    } catch (error) {
      if (!(error instanceof ApiError && error.isClientError())) {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  const rows = query.data?.results ?? [];

  return (
    <div>
      {contestId != null ? (
        <ContestDialog
          updateId={contestId}
          open={contestId != null}
          onOpenChange={(open) => {
            if (!open) setContestId(null);
          }}
        />
      ) : null}

      <PageHeader
        title={t("updates.title")}
        breadcrumbs={[
          { label: t("common:nav.groups.operations") },
          { label: t("updates.breadcrumb") },
        ]}
      />

      <div className="space-y-4 p-6">
        <CheckboxLabel>
          <Checkbox
            checked={unseenOnly}
            onCheckedChange={(v) => toggleUnseen(v === true)}
            aria-label={t("updates.filters.unseen_only")}
          />
          {t("updates.filters.unseen_only")}
        </CheckboxLabel>

        {query.isError ? (
          <ErrorState
            description={t("updates.load_failed")}
            onRetry={() => query.refetch()}
            retrying={query.isFetching}
          />
        ) : query.isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : rows.length === 0 ? (
          <EmptyState title={t("updates.empty_title")} description={t("updates.empty_hint")} />
        ) : (
          <ActivityList as="ol">
            {rows.map((update) => (
              <li key={update.id} className="flex items-start justify-between gap-4 px-4 py-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-foreground text-sm font-medium">
                      {update.block.property_name ?? t("updates.unknown_property")}
                    </span>
                    <Badge variant={update.kind === "cancelled" ? "destructive" : "secondary"}>
                      {t(`updates.kind.${update.kind}`)}
                    </Badge>
                    <Badge variant="outline">{t(`blocks.kind.${update.block.kind}`)}</Badge>
                    {update.contested ? (
                      <Badge variant="destructive">{t("updates.contested_badge")}</Badge>
                    ) : null}
                    {!update.is_seen ? (
                      <Badge variant="default">{t("updates.unseen_badge")}</Badge>
                    ) : null}
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {formatDate(update.block.date_from)} – {formatDate(update.block.date_to)}
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {formatDateTime(update.created_at)}
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleSeenToggle(update)}
                    disabled={markSeen.isPending || markUnseen.isPending}
                  >
                    {update.is_seen
                      ? t("updates.actions.mark_unseen")
                      : t("updates.actions.mark_seen")}
                  </Button>
                  <ContestButton
                    disabled={!hasRole}
                    disabledReason={t("common:errors.reservations_role_required")}
                    label={t("updates.actions.contest")}
                    onClick={() => setContestId(update.id)}
                  />
                </div>
              </li>
            ))}
          </ActivityList>
        )}
      </div>
    </div>
  );
}

interface ContestButtonProps {
  disabled: boolean;
  disabledReason: string;
  label: string;
  onClick: () => void;
}

function ContestButton({ disabled, disabledReason, label, onClick }: ContestButtonProps) {
  const button = (
    <Button variant="outline" size="sm" onClick={onClick} disabled={disabled}>
      {label}
    </Button>
  );
  if (!disabled) return button;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block">{button}</span>
      </TooltipTrigger>
      <TooltipContent>{disabledReason}</TooltipContent>
    </Tooltip>
  );
}
