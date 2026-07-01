import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FactList, FactRow } from "@/components/data/FactList";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import {
  useDeleteRatePeriod,
  useDeleteRateBand,
  usePropertySettings,
  useRatePlanDetail,
} from "../hooks";
import { formatPartyGaps } from "../coverage";
import { RatePeriodFormDialog } from "./RatePeriodFormDialog";
import { RateBandFormDialog } from "./RateBandFormDialog";
import type { RatePeriod, RateBand } from "../schemas";

export function ActiveBadge({ isActive }: { isActive: boolean | undefined }) {
  const { t } = useTranslation("properties");
  return isActive ? (
    <Badge variant="secondary">{t("pricing.active_badge")}</Badge>
  ) : (
    <Badge variant="outline">{t("pricing.inactive_badge")}</Badge>
  );
}

function RatePeriodBlock({
  period,
  canWrite,
  onEdit,
  onDelete,
  onAddRule,
  onEditBand,
  onDeleteBand,
}: {
  period: RatePeriod;
  canWrite: boolean;
  onEdit: (period: RatePeriod) => void;
  onDelete: (period: RatePeriod) => void;
  onAddRule: (period: RatePeriod) => void;
  onEditBand: (rule: RateBand) => void;
  onDeleteBand: (rule: RateBand) => void;
}) {
  const { t } = useTranslation("properties");
  const poa = t("pricing.rate_period.poa");
  const dash = t("common.unset");
  const placeholder = t("pricing.rate_period.nights_min_placeholder");
  const gaps = period.coverage_gaps ?? [];
  return (
    <div className="border-border bg-card space-y-3 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h4 className="text-foreground text-sm font-semibold">
            {period.name || t("pricing.rate_period.untitled")}
          </h4>
          <p className="text-muted-foreground text-xs">
            {formatDate(period.date_from)} – {formatDate(period.date_to)}
          </p>
          <p className="text-muted-foreground mt-1 text-xs">
            {period.min_nights != null || period.max_nights != null
              ? t("pricing.rate_period.nights_range", {
                  min: period.min_nights ?? placeholder,
                  max: period.max_nights ?? placeholder,
                })
              : t("pricing.rate_period.any_length")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ActiveBadge isActive={period.is_active} />
          {canWrite ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2"
                  aria-label={t("pricing.rate_period.row.menu_label")}
                >
                  ···
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onEdit(period)}>
                  {t("pricing.rate_period.row.edit")}
                </DropdownMenuItem>
                <DropdownMenuItem className="text-destructive" onClick={() => onDelete(period)}>
                  {t("pricing.rate_period.row.delete")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>
      {gaps.length > 0 ? (
        <p
          role="status"
          className="border-warning/40 bg-warning/10 text-warning rounded-md border px-3 py-2 text-xs"
        >
          {t("pricing.rate_period.coverage_gap_warning", { ranges: formatPartyGaps(gaps) })}
        </p>
      ) : null}
      {period.bands.length === 0 ? (
        <p className="text-muted-foreground text-xs italic">{t("pricing.rate_period.no_rules")}</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-muted-foreground text-left">
            <tr>
              <th className="py-1 pr-2 font-medium">{t("pricing.rules_table.party")}</th>
              <th className="py-1 pr-2 font-medium">{t("pricing.rules_table.nightly")}</th>
              <th className="py-1 font-medium">{t("pricing.rules_table.weekly")}</th>
              {canWrite ? (
                <th className="py-1 text-right font-medium">
                  <span className="sr-only">{t("pricing.rules_table.actions")}</span>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {period.bands.map((rule) => (
              <tr key={rule.id} className="border-border border-t">
                <td className="py-1 pr-2">
                  {rule.min_party ?? placeholder}–{rule.max_party ?? placeholder}
                </td>
                <td className="py-1 pr-2">{rule.is_poa ? poa : (rule.nightly ?? dash)}</td>
                <td className="py-1">{rule.is_poa ? poa : (rule.weekly ?? dash)}</td>
                {canWrite ? (
                  <td className="py-1 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2"
                          aria-label={t("pricing.rule.row.menu_label")}
                        >
                          ···
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => onEditBand(rule)}>
                          {t("pricing.rule.row.edit")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => onDeleteBand(rule)}
                        >
                          {t("pricing.rule.row.delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canWrite ? (
        <Button variant="ghost" size="sm" onClick={() => onAddRule(period)}>
          {t("pricing.rule.add_button")}
        </Button>
      ) : null}
    </div>
  );
}

export function RatePlanDetailPanel({
  propertyId,
  ratePlanId,
  onBack,
  canWrite,
}: {
  propertyId: number;
  ratePlanId: number;
  onBack: () => void;
  canWrite: boolean;
}) {
  const { t } = useTranslation("properties");
  const detail = useRatePlanDetail(ratePlanId);
  const settings = usePropertySettings(propertyId);
  // GAP-026: the property's effective currency, used to flag (softly, never
  // blocking) a season whose currency diverges from it.
  const propertyCurrencyCode = settings.data?.currency_code ?? null;
  const seasonCurrencyCode = detail.data?.currency_code ?? null;
  const currencyMismatch =
    !!propertyCurrencyCode &&
    !!seasonCurrencyCode &&
    propertyCurrencyCode.toUpperCase() !== seasonCurrencyCode.toUpperCase();
  // GAP-035: the season's basis + the property's group-resolved effective
  // commission/tax drive the rate-band form's live net↔gross derivation hint.
  const seasonPriceBasis = detail.data?.price_basis ?? null;
  const commission = settings.data?.commission ?? null;
  const tax = settings.data?.tax ?? null;
  const dash = t("common.unset");

  const deletePeriodMutation = useDeleteRatePeriod(ratePlanId);
  const deleteRuleMutation = useDeleteRateBand(ratePlanId);

  const [addPeriodOpen, setAddPeriodOpen] = useState(false);
  const [editingPeriod, setEditingPeriod] = useState<RatePeriod | null>(null);
  const [deletingPeriod, setDeletingPeriod] = useState<RatePeriod | null>(null);
  const [addingRulePeriod, setAddingRulePeriod] = useState<RatePeriod | null>(null);
  const [editingBand, setEditingBand] = useState<RateBand | null>(null);
  const [deletingBand, setDeletingBand] = useState<RateBand | null>(null);

  const handleDeletePeriod = async () => {
    if (!deletingPeriod) return;
    try {
      await deletePeriodMutation.mutateAsync({ periodId: deletingPeriod.id });
      toast.success(t("pricing.rate_period.toasts.deleted"));
      setDeletingPeriod(null);
    } catch {
      toast.error(t("pricing.rate_period.toasts.delete_failed"));
    }
  };

  const handleDeleteRule = async () => {
    if (!deletingBand) return;
    try {
      await deleteRuleMutation.mutateAsync({ bandId: deletingBand.id });
      toast.success(t("pricing.rule.toasts.deleted"));
      setDeletingBand(null);
    } catch {
      toast.error(t("pricing.rule.toasts.delete_failed"));
    }
  };

  const addPeriodButton = canWrite ? (
    <Button size="sm" onClick={() => setAddPeriodOpen(true)}>
      {t("pricing.rate_period.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("pricing.rate_period.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("pricing.rate_period.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={onBack}>
        {t("pricing.season_detail.back")}
      </Button>
      {detail.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : detail.isError || !detail.data ? (
        <ErrorState
          title={t("pricing.season_detail.error_title")}
          description={t("pricing.season_detail.error_body")}
          onRetry={() => detail.refetch()}
        />
      ) : (
        <>
          <FactList>
            <FactRow label={t("pricing.season_detail.fields.name")} value={detail.data.name} />
            <FactRow
              label={t("pricing.season_detail.fields.currency")}
              value={detail.data.currency_code ?? dash}
            />
            <FactRow
              label={t("pricing.season_detail.fields.price_basis")}
              value={detail.data.price_basis ?? dash}
            />
            <FactRow
              label={t("pricing.season_detail.fields.effective")}
              value={`${formatDate(detail.data.effective_from)} – ${formatDate(detail.data.effective_to)}`}
            />
            <FactRow
              label={t("pricing.season_detail.fields.status")}
              value={<ActiveBadge isActive={detail.data.is_active} />}
            />
          </FactList>
          {currencyMismatch ? (
            <p
              role="status"
              className="border-warning/40 bg-warning/10 text-warning rounded-md border px-3 py-2 text-xs"
            >
              {t("pricing.season_detail.currency_mismatch", {
                season: seasonCurrencyCode,
                property: propertyCurrencyCode,
              })}
            </p>
          ) : null}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-foreground text-sm font-semibold">
                {t("pricing.season_detail.rate_periods_heading")}
              </h3>
              {addPeriodButton}
            </div>
            {detail.data.periods.length === 0 ? (
              <EmptyState title={t("pricing.season_detail.empty_rate_periods")} />
            ) : (
              detail.data.periods.map((period) => (
                <RatePeriodBlock
                  key={period.id}
                  period={period}
                  canWrite={canWrite}
                  onEdit={setEditingPeriod}
                  onDelete={setDeletingPeriod}
                  onAddRule={setAddingRulePeriod}
                  onEditBand={setEditingBand}
                  onDeleteBand={setDeletingBand}
                />
              ))
            )}
          </div>
        </>
      )}

      {addPeriodOpen ? (
        <RatePeriodFormDialog
          ratePlanId={ratePlanId}
          open={addPeriodOpen}
          onOpenChange={setAddPeriodOpen}
          mode="create"
        />
      ) : null}
      {editingPeriod ? (
        <RatePeriodFormDialog
          ratePlanId={ratePlanId}
          open={!!editingPeriod}
          onOpenChange={(o) => !o && setEditingPeriod(null)}
          mode="edit"
          period={editingPeriod}
        />
      ) : null}
      {addingRulePeriod ? (
        <RateBandFormDialog
          ratePlanId={ratePlanId}
          periodId={addingRulePeriod.id}
          open={!!addingRulePeriod}
          onOpenChange={(o) => !o && setAddingRulePeriod(null)}
          mode="create"
          currencyCode={seasonCurrencyCode}
          priceBasis={seasonPriceBasis}
          commission={commission}
          tax={tax}
        />
      ) : null}
      {editingBand ? (
        <RateBandFormDialog
          ratePlanId={ratePlanId}
          periodId={editingBand.period}
          open={!!editingBand}
          onOpenChange={(o) => !o && setEditingBand(null)}
          mode="edit"
          rule={editingBand}
          currencyCode={seasonCurrencyCode}
          priceBasis={seasonPriceBasis}
          commission={commission}
          tax={tax}
        />
      ) : null}
      {deletingPeriod ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingPeriod(null)}
          onConfirm={handleDeletePeriod}
          title={t("pricing.rate_period.delete_confirm.title")}
          description={t("pricing.rate_period.delete_confirm.description")}
          confirmLabel={t("pricing.rate_period.delete_confirm.confirm")}
          destructive
          busy={deletePeriodMutation.isPending}
        />
      ) : null}
      {deletingBand ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingBand(null)}
          onConfirm={handleDeleteRule}
          title={t("pricing.rule.delete_confirm.title")}
          description={t("pricing.rule.delete_confirm.description")}
          confirmLabel={t("pricing.rule.delete_confirm.confirm")}
          destructive
          busy={deleteRuleMutation.isPending}
        />
      ) : null}
    </div>
  );
}
