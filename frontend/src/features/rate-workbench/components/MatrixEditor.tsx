import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { formatDate } from "@/lib/format/date";
import type { CommissionInput, TaxInput } from "@/lib/pricing/netGross";
import { RateBandFormDialog } from "@/features/properties/components/RateBandFormDialog";
import { useDeleteRateBand } from "@/features/properties/hooks";
import { formatPartyGaps } from "@/features/properties/coverage";
import type { RatePeriod, RatePlanDetail, RateBand } from "@/features/properties/schemas";
import { useOptimisticBandNightly } from "../hooks";
import { bandLabel, buildMatrix, type MatrixCell as CellModel } from "../matrixModel";
import { MatrixCell } from "./MatrixCell";

interface MatrixEditorProps {
  ratePlanId: number;
  seasons: RatePlanDetail[];
  canWrite: boolean;
  commission: CommissionInput | null;
  tax: TaxInput | null;
}

/** Uncovered-party warning for each active period that has bands but a gap. */
function periodLabel(period: RatePeriod): string {
  return period.name || `${formatDate(period.date_from)} – ${formatDate(period.date_to)}`;
}

/**
 * Segment-first rate matrix for a chosen season. Rate periods are rows (each
 * owns an inclusive date range), party bands columns; a cell fast-edits nightly
 * inline (optimistic) or opens the rule dialog for structural edits. New bands
 * are always seeded on the grid's period/band axes, so raggedness is never
 * introduced here.
 */
export function MatrixEditor({
  ratePlanId,
  seasons,
  canWrite,
  commission,
  tax,
}: MatrixEditorProps) {
  const { t } = useTranslation("properties");
  const season = seasons.find((s) => s.id === ratePlanId) ?? null;
  const periods = useMemo(() => season?.periods ?? [], [season]);

  const currencyCode = season?.currency_code ?? null;
  const priceBasis = season?.price_basis ?? null;

  const matrix = useMemo(() => buildMatrix(periods), [periods]);
  const gapPeriods = periods.filter((p) => (p.coverage_gaps ?? []).length > 0);

  const nightly = useOptimisticBandNightly(ratePlanId);
  const deleteRule = useDeleteRateBand(ratePlanId);

  const [creatingCell, setCreatingCell] = useState<CellModel | null>(null);
  const [editingBand, setEditingBand] = useState<RateBand | null>(null);
  const [deletingBand, setDeletingBand] = useState<RateBand | null>(null);

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

  if (!season || periods.length === 0) {
    return <EmptyState title={t("rate_workbench.matrix.no_periods")} />;
  }

  return (
    <div className="space-y-3">
      {gapPeriods.length > 0 ? (
        <ul
          role="status"
          className="border-warning/40 bg-warning/10 text-warning space-y-1 rounded-md border px-3 py-2 text-xs"
        >
          {gapPeriods.map((p) => (
            <li key={p.id}>
              {t("rate_workbench.matrix.coverage_gap", {
                period: periodLabel(p),
                ranges: formatPartyGaps(p.coverage_gaps ?? []),
              })}
            </li>
          ))}
        </ul>
      ) : null}

      {matrix.bands.length === 0 ? (
        <EmptyState title={t("rate_workbench.matrix.no_rules")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="text-muted-foreground text-left">
                <th className="py-2 pr-3 font-medium">{t("rate_workbench.matrix.segment")}</th>
                {matrix.bands.map((b) => (
                  <th key={bandLabel(b) ?? "any"} className="px-2 py-2 font-medium">
                    {bandLabel(b) ?? t("rate_workbench.matrix.any_party")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.segments.map((segment, row) => (
                <tr key={segment.periodId} className="border-border border-t">
                  <td className="py-2 pr-3 align-middle whitespace-nowrap">
                    {formatDate(segment.dateFrom)} – {formatDate(segment.dateTo)}
                    {segment.name ? (
                      <span className="text-muted-foreground ml-2">{segment.name}</span>
                    ) : null}
                  </td>
                  {matrix.cells[row].map((cell, col) => (
                    <td key={`${row}-${col}`} className="px-2 py-1 align-middle">
                      <MatrixCell
                        cell={cell}
                        currencyCode={currencyCode}
                        canWrite={canWrite}
                        onCommitNightly={(bandId, value) =>
                          nightly.mutate({ bandId, nightly: value })
                        }
                        onEditBand={setEditingBand}
                        onFill={setCreatingCell}
                        onDeleteBand={setDeletingBand}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creatingCell ? (
        <RateBandFormDialog
          ratePlanId={ratePlanId}
          periodId={creatingCell.periodId}
          open={!!creatingCell}
          onOpenChange={(o) => !o && setCreatingCell(null)}
          mode="create"
          defaults={{
            min_party: creatingCell.minParty ?? 1,
            max_party: creatingCell.maxParty ?? 1,
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
    </div>
  );
}
