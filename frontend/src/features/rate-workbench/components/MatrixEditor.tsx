import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { formatDate, todayIso } from "@/lib/format/date";
import { periodLabel } from "@/features/properties/periodLabel";
import type { CommissionInput, TaxInput } from "@/lib/pricing/netGross";
import { RateBandFormDialog } from "@/features/properties/components/RateBandFormDialog";
import { RatePeriodFormDialog } from "@/features/properties/components/RatePeriodFormDialog";
import { useDeleteRateBand, useDeleteRatePeriod } from "@/features/properties/hooks";
import { formatPartyGaps } from "@/features/properties/coverage";
import type { RatePeriod, RatePlanDetail, RateBand } from "@/features/properties/schemas";
import { useOptimisticBandPrice } from "../hooks";
import { bandLabel, buildMatrix, isHistoricalPeriod } from "../matrixModel";
import { MatrixCell } from "./MatrixCell";

interface MatrixEditorProps {
  ratePlanId: number;
  seasons: RatePlanDetail[];
  canWrite: boolean;
  commission: CommissionInput | null;
  tax: TaxInput | null;
  /** Opens the parent's period-create dialog; a zero-period season renders an
   * "Add period" CTA in its empty state when this is provided. */
  onAddPeriod?: () => void;
}

/** Party-range prefill for a new band on this period. The serializer's
 * coverage_gaps are authoritative (inclusive, disjoint from existing bands),
 * so the first gap wins; otherwise seed just above the covered range. Falls
 * back to 1 when the period has no bounded coverage to extend. */
function bandCreateSeed(period: RatePeriod): { minParty: number; maxParty: number } {
  const firstGap = (period.coverage_gaps ?? [])[0];
  if (firstGap) return { minParty: firstGap[0], maxParty: firstGap[1] };
  const maxes = (period.bands ?? []).map((b) => b.max_party);
  if (maxes.length === 0 || maxes.some((m) => m == null)) return { minParty: 1, maxParty: 1 };
  const next = Math.max(...(maxes as number[])) + 1;
  return { minParty: next, maxParty: next };
}

/** Rate-period lifecycle menu (edit / delete), ported from the retired Pricing
 * tab's RatePlanDetailPanel. Rendered both in the grid row-header (when the
 * plan has bands) and in the band-less period list, so a just-created,
 * still-empty period stays editable/deletable. */
function PeriodActionsMenu({
  period,
  onEdit,
  onDelete,
}: {
  period: RatePeriod;
  onEdit: (period: RatePeriod) => void;
  onDelete: (period: RatePeriod) => void;
}) {
  const { t } = useTranslation("properties");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2"
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
  );
}

/**
 * Segment-first rate matrix for a chosen season. Rate periods are rows (each
 * owns an inclusive date range), party bands columns; a cell fast-edits its
 * nightly and weekly prices inline (optimistic) or opens the rule dialog for
 * structural edits. New bands are always seeded on the grid's period/band
 * axes, so raggedness is never introduced here.
 */
export function MatrixEditor({
  ratePlanId,
  seasons,
  canWrite,
  commission,
  tax,
  onAddPeriod,
}: MatrixEditorProps) {
  const { t } = useTranslation("properties");
  const season = seasons.find((s) => s.id === ratePlanId) ?? null;
  const periods = useMemo(() => season?.periods ?? [], [season]);

  const currencyCode = season?.currency_code ?? null;
  const priceBasis = season?.price_basis ?? null;
  // Flat plans price one rate per period (party size ignored): the party
  // columns collapse to a single "Flat rate" column and the occupancy-band
  // affordances (trailing "+", coverage-gap chips) are hidden — adding a
  // second band is a mode switch, not an in-grid action (the backend 400s it).
  const pricesByOccupancy = season?.prices_by_occupancy ?? false;

  // Historical periods (window fully elapsed) clutter the grid with rates that
  // can no longer change. Hide them by default; a toggle reveals them read-only.
  // `today` is snapshotted once so filtering/memoisation stay stable per mount.
  const today = useMemo(() => todayIso(), []);
  const [showHistorical, setShowHistorical] = useState(false);
  const historicalIds = useMemo(
    () => new Set(periods.filter((p) => isHistoricalPeriod(p, today)).map((p) => p.id)),
    [periods, today],
  );
  const visiblePeriods = useMemo(
    () => (showHistorical ? periods : periods.filter((p) => !historicalIds.has(p.id))),
    [periods, showHistorical, historicalIds],
  );
  // The band-create CTA (bandless plan) always targets a live period — you
  // cannot add a band to a locked historical one.
  const firstEditablePeriod = visiblePeriods.find((p) => !historicalIds.has(p.id)) ?? null;

  const matrix = useMemo(() => buildMatrix(visiblePeriods), [visiblePeriods]);
  // Coverage gaps are actionable only on live periods — a historical one is
  // locked, so warning about its gaps would only offer a dead-end "fill" chip.
  const gapPeriods = pricesByOccupancy
    ? visiblePeriods.filter((p) => !historicalIds.has(p.id) && (p.coverage_gaps ?? []).length > 0)
    : [];

  const price = useOptimisticBandPrice(ratePlanId);
  const deleteRule = useDeleteRateBand(ratePlanId);
  const deletePeriod = useDeleteRatePeriod(ratePlanId);

  // One create-dialog state for all three entry points: empty-cell fill,
  // the trailing-column "+", and coverage-gap chips.
  const [creatingBand, setCreatingBand] = useState<{
    periodId: number;
    minParty: number;
    maxParty: number;
  } | null>(null);
  const [editingBand, setEditingBand] = useState<RateBand | null>(null);
  const [deletingBand, setDeletingBand] = useState<RateBand | null>(null);
  // Period lifecycle, ported from the retired Pricing tab's RatePlanDetailPanel.
  const [editingPeriod, setEditingPeriod] = useState<RatePeriod | null>(null);
  const [deletingPeriod, setDeletingPeriod] = useState<RatePeriod | null>(null);

  const handleDelete = async () => {
    if (!deletingBand) return;
    try {
      await deleteRule.mutateAsync({ bandId: deletingBand.id });
      toast.success(t("rate_workbench.matrix.deleted"));
      setDeletingBand(null);
    } catch {
      toast.error(t("rate_workbench.matrix.save_failed"));
    }
  };

  const handleDeletePeriod = async () => {
    if (!deletingPeriod) return;
    try {
      await deletePeriod.mutateAsync({ periodId: deletingPeriod.id });
      toast.success(t("pricing.rate_period.toasts.deleted"));
      setDeletingPeriod(null);
    } catch {
      toast.error(t("pricing.rate_period.toasts.delete_failed"));
    }
  };

  if (!season || periods.length === 0) {
    return (
      <EmptyState
        title={t("rate_workbench.matrix.no_periods")}
        description={season ? t("rate_workbench.matrix.no_periods_hint") : undefined}
        action={
          season && onAddPeriod ? (
            canWrite ? (
              <Button onClick={onAddPeriod}>{t("rate_workbench.matrix.add_period")}</Button>
            ) : (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button disabled>{t("rate_workbench.matrix.add_period")}</Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {t("rate_workbench.matrix.add_period_disabled_tooltip")}
                </TooltipContent>
              </Tooltip>
            )
          ) : undefined
        }
      />
    );
  }

  const historicalToggle =
    historicalIds.size > 0 ? (
      <div className="flex justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-muted-foreground text-xs"
          aria-pressed={showHistorical}
          onClick={() => setShowHistorical((v) => !v)}
        >
          {showHistorical
            ? t("rate_workbench.matrix.hide_historical")
            : t("rate_workbench.matrix.show_historical", { count: historicalIds.size })}
        </Button>
      </div>
    ) : null;

  return (
    <div className="space-y-3">
      {historicalToggle}
      {visiblePeriods.length === 0 ? (
        <EmptyState
          title={t("rate_workbench.matrix.all_historical_title")}
          description={t("rate_workbench.matrix.all_historical_body", {
            count: historicalIds.size,
          })}
        />
      ) : (
        <>
          {gapPeriods.length > 0 ? (
            // Interactive chips must NOT sit in a live region (controls inside
            // role="status" get re-announced on every render), so only the
            // viewer's text-only variant is a status region.
            <ul
              role={canWrite ? undefined : "status"}
              className="border-warning/40 bg-warning/10 text-warning space-y-1 rounded-md border px-3 py-2 text-xs"
            >
              {gapPeriods.map((p) =>
                canWrite ? (
                  // Actionable warning: each gap is a chip that opens the band
                  // dialog prefilled with that exact inclusive party range.
                  <li key={p.id} className="flex flex-wrap items-center gap-1.5">
                    <span>
                      {t("rate_workbench.matrix.coverage_gap_intro", { period: periodLabel(p) })}
                    </span>
                    {(p.coverage_gaps ?? []).map(([low, high]) => {
                      const range = formatPartyGaps([[low, high]]);
                      return (
                        <Button
                          key={range}
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-5 px-1.5 text-xs"
                          aria-label={t("rate_workbench.matrix.fill_gap_chip", { range })}
                          onClick={() =>
                            setCreatingBand({ periodId: p.id, minParty: low, maxParty: high })
                          }
                        >
                          {range}
                        </Button>
                      );
                    })}
                  </li>
                ) : (
                  <li key={p.id}>
                    {t("rate_workbench.matrix.coverage_gap", {
                      period: periodLabel(p),
                      ranges: formatPartyGaps(p.coverage_gaps ?? []),
                    })}
                  </li>
                ),
              )}
            </ul>
          ) : null}

          {matrix.bands.length === 0 ? (
            <div className="space-y-3">
              {/* No bands anywhere → the grid renders no period rows, so surface the
              periods (with their lifecycle menu) here; else a just-created
              period would be unreachable for edit/delete. Writer-only. */}
              {canWrite ? (
                <ul className="divide-border border-border divide-y rounded-md border">
                  {visiblePeriods.map((p) => {
                    const locked = historicalIds.has(p.id);
                    return (
                      <li
                        key={p.id}
                        className="flex items-center justify-between gap-2 px-3 py-2 text-xs"
                      >
                        <span className={locked ? "text-muted-foreground" : "text-foreground"}>
                          {formatDate(p.date_from)} – {formatDate(p.date_to)}
                          {p.name ? (
                            <span className="text-muted-foreground ml-2">{p.name}</span>
                          ) : null}
                        </span>
                        {locked ? (
                          <Badge variant="outline">
                            {t("rate_workbench.matrix.historical_badge")}
                          </Badge>
                        ) : (
                          <PeriodActionsMenu
                            period={p}
                            onEdit={setEditingPeriod}
                            onDelete={setDeletingPeriod}
                          />
                        )}
                      </li>
                    );
                  })}
                </ul>
              ) : null}
              <EmptyState
                title={t("rate_workbench.matrix.no_rules")}
                action={
                  canWrite && firstEditablePeriod ? (
                    <Button
                      onClick={() =>
                        setCreatingBand({
                          periodId: firstEditablePeriod.id,
                          ...bandCreateSeed(firstEditablePeriod),
                        })
                      }
                    >
                      {t("rate_workbench.matrix.add_band")}
                    </Button>
                  ) : undefined
                }
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="text-muted-foreground text-left">
                    <th className="py-2 pr-3 font-medium">{t("rate_workbench.matrix.segment")}</th>
                    {matrix.bands.map((b) => {
                      const label = bandLabel(b);
                      return (
                        <th key={label ?? "any"} className="px-2 py-2 font-medium">
                          {!pricesByOccupancy
                            ? t("rate_workbench.matrix.flat_rate")
                            : label != null
                              ? t("rate_workbench.matrix.party_pax", { range: label })
                              : t("rate_workbench.matrix.any_party")}
                        </th>
                      );
                    })}
                    {canWrite ? (
                      <th className="py-2 pl-2">
                        <span className="sr-only">{t("rate_workbench.matrix.add_band")}</span>
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {matrix.segments.map((segment, row) => {
                    const rowCells = matrix.cells[row];
                    // The "+" always sits right of the row's last band: when an
                    // empty fillable cell is there, its own "+" is the add
                    // affordance; only otherwise (last band in the final column,
                    // or everything to its right covered) does the trailing
                    // column carry one. And when the create seed itself would
                    // overlap one of the period's bands (an unbounded band
                    // already covers it), saving could only 4xx — no "+" at all.
                    const lastBandCol = rowCells.reduce((acc, c, i) => (c.band ? i : acc), -1);
                    const period = periods.find((p) => p.id === segment.periodId);
                    const seed = period ? bandCreateSeed(period) : { minParty: 1, maxParty: 1 };
                    const seedCovered = (period?.bands ?? []).some(
                      (b) =>
                        (b.min_party == null || b.min_party <= seed.maxParty) &&
                        (b.max_party == null || b.max_party >= seed.minParty),
                    );
                    // A historical period is locked: no inline edits, no add "+",
                    // no lifecycle menu — just a "Past" marker (the backend 400s any
                    // write regardless).
                    const rowLocked = historicalIds.has(segment.periodId);
                    const showTrailingAdd =
                      pricesByOccupancy &&
                      !rowLocked &&
                      lastBandCol >= 0 &&
                      !seedCovered &&
                      !rowCells.some((c, i) => i > lastBandCol && c.fillable);
                    return (
                      <tr key={segment.periodId} className="border-border border-t">
                        <td className="py-2 pr-3 align-middle whitespace-nowrap">
                          <span className="inline-flex items-center gap-2">
                            <span className={rowLocked ? "text-muted-foreground" : undefined}>
                              {formatDate(segment.dateFrom)} – {formatDate(segment.dateTo)}
                              {segment.name ? (
                                <span className="text-muted-foreground ml-2">{segment.name}</span>
                              ) : null}
                            </span>
                            {rowLocked ? (
                              <Badge variant="outline">
                                {t("rate_workbench.matrix.historical_badge")}
                              </Badge>
                            ) : canWrite && period ? (
                              <PeriodActionsMenu
                                period={period}
                                onEdit={setEditingPeriod}
                                onDelete={setDeletingPeriod}
                              />
                            ) : null}
                          </span>
                        </td>
                        {rowCells.map((cell, col) => (
                          <td key={`${row}-${col}`} className="px-2 py-1 align-middle">
                            <MatrixCell
                              cell={cell}
                              currencyCode={currencyCode}
                              canWrite={canWrite && !rowLocked}
                              onCommitPrice={(bandId, field, value) =>
                                price.mutate({ bandId, field, value })
                              }
                              onEditBand={setEditingBand}
                              onFill={(c) =>
                                setCreatingBand({
                                  periodId: c.periodId,
                                  minParty: c.minParty ?? 1,
                                  maxParty: c.maxParty ?? 1,
                                })
                              }
                              onDeleteBand={setDeletingBand}
                            />
                          </td>
                        ))}
                        {canWrite ? (
                          <td className="py-1 pl-2 align-middle">
                            {showTrailingAdd ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon-sm"
                                className="text-muted-foreground/60"
                                aria-label={t("rate_workbench.matrix.add_band_for", {
                                  period: periodLabel({
                                    name: segment.name,
                                    date_from: segment.dateFrom,
                                    date_to: segment.dateTo,
                                  }),
                                })}
                                onClick={() =>
                                  setCreatingBand({ periodId: segment.periodId, ...seed })
                                }
                              >
                                <Plus className="h-3.5 w-3.5" />
                              </Button>
                            ) : null}
                          </td>
                        ) : null}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {creatingBand ? (
        <RateBandFormDialog
          ratePlanId={ratePlanId}
          periodId={creatingBand.periodId}
          open={!!creatingBand}
          onOpenChange={(o) => !o && setCreatingBand(null)}
          mode="create"
          defaults={{
            min_party: creatingBand.minParty,
            max_party: creatingBand.maxParty,
          }}
          currencyCode={currencyCode}
          priceBasis={priceBasis}
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
          currencyCode={currencyCode}
          priceBasis={priceBasis}
          commission={commission}
          tax={tax}
        />
      ) : null}
      {deletingBand ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingBand(null)}
          onConfirm={handleDelete}
          title={t("rate_workbench.matrix.delete_confirm.title")}
          description={t("rate_workbench.matrix.delete_confirm.description")}
          confirmLabel={t("rate_workbench.matrix.delete_confirm.confirm")}
          destructive
          busy={deleteRule.isPending}
        />
      ) : null}
      {editingPeriod ? (
        <RatePeriodFormDialog
          ratePlanId={ratePlanId}
          open
          onOpenChange={(o) => !o && setEditingPeriod(null)}
          mode="edit"
          period={editingPeriod}
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
          busy={deletePeriod.isPending}
        />
      ) : null}
    </div>
  );
}
