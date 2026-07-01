import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { formatDate } from "@/lib/format/date";
import type { CommissionInput, TaxInput } from "@/lib/pricing/netGross";
import { RateRuleFormDialog } from "@/features/properties/components/RateRuleFormDialog";
import { useDeleteRateRule } from "@/features/properties/hooks";
import type { RatePlanDetail, RateRule } from "@/features/properties/schemas";
import { useOptimisticRuleNightly } from "../hooks";
import { bandLabel, buildMatrix, type MatrixCell as CellModel } from "../matrixModel";
import { MatrixCell } from "./MatrixCell";

interface MatrixEditorProps {
  seasonId: number;
  seasons: RatePlanDetail[];
  canWrite: boolean;
  changeoverDay: string | null;
  minNightsRental: number | null;
  commission: CommissionInput | null;
  tax: TaxInput | null;
}

/**
 * Segment-first (Option A) rate matrix for a chosen season + card. Date segments
 * are rows, party bands columns; a cell fast-edits nightly inline (optimistic)
 * or opens the rule dialog for structural edits. New rules are always seeded on
 * the grid's segment/band axes, so raggedness is never introduced here; existing
 * overlapping segments are flagged and edited as their own rules.
 */
export function MatrixEditor({
  seasonId,
  seasons,
  canWrite,
  changeoverDay,
  minNightsRental,
  commission,
  tax,
}: MatrixEditorProps) {
  const { t } = useTranslation("properties");
  const season = seasons.find((s) => s.id === seasonId) ?? null;
  const cards = season?.cards ?? [];
  const [cardId, setCardId] = useState<number | null>(cards[0]?.id ?? null);
  const selectedCard = cards.find((c) => c.id === cardId) ?? cards[0] ?? null;

  const currencyCode = season?.currency_code ?? null;
  const priceBasis = season?.price_basis ?? null;

  const matrix = useMemo(() => (selectedCard ? buildMatrix(selectedCard) : null), [selectedCard]);

  const nightly = useOptimisticRuleNightly(seasonId);
  const deleteRule = useDeleteRateRule(seasonId);

  const [creatingCell, setCreatingCell] = useState<CellModel | null>(null);
  const [editingRule, setEditingRule] = useState<RateRule | null>(null);
  const [deletingRule, setDeletingRule] = useState<RateRule | null>(null);

  const handleDelete = async () => {
    if (!deletingRule) return;
    try {
      await deleteRule.mutateAsync({ ruleId: deletingRule.id });
      toast.success(t("rate_workbench.matrix.deleted"));
      setDeletingRule(null);
    } catch {
      toast.error(t("rate_workbench.matrix.save_failed"));
    }
  };

  if (!season || cards.length === 0 || !selectedCard || !matrix) {
    return <EmptyState title={t("rate_workbench.matrix.no_cards")} />;
  }

  return (
    <div className="space-y-3">
      {cards.length > 1 ? (
        <div className="flex justify-end">
          <Select value={String(selectedCard.id)} onValueChange={(v) => setCardId(Number(v))}>
            <SelectTrigger
              className="w-[200px]"
              aria-label={t("rate_workbench.matrix.card_picker")}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {cards.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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
                <tr
                  key={`${segment.dateFrom}|${segment.dateTo}`}
                  className="border-border border-t"
                >
                  <td className="py-2 pr-3 align-middle whitespace-nowrap">
                    {formatDate(segment.dateFrom)} – {formatDate(segment.dateTo)}
                  </td>
                  {matrix.cells[row].map((cell, col) => (
                    <td key={`${row}-${col}`} className="px-2 py-1 align-middle">
                      <MatrixCell
                        cell={cell}
                        currencyCode={currencyCode}
                        canWrite={canWrite}
                        onCommitNightly={(ruleId, value) =>
                          nightly.mutate({ ruleId, nightly: value })
                        }
                        onEditRule={setEditingRule}
                        onFill={setCreatingCell}
                        onDeleteRule={setDeletingRule}
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
        <RateRuleFormDialog
          seasonId={seasonId}
          cardId={selectedCard.id}
          open={!!creatingCell}
          onOpenChange={(o) => !o && setCreatingCell(null)}
          mode="create"
          defaults={{
            date_from: creatingCell.dateFrom,
            date_to: creatingCell.dateTo,
            min_party: creatingCell.minParty ?? 1,
            max_party: creatingCell.maxParty ?? 1,
          }}
          changeoverDay={changeoverDay}
          minNightsRental={minNightsRental}
          currencyCode={currencyCode}
          priceBasis={priceBasis}
          commission={commission}
          tax={tax}
        />
      ) : null}
      {editingRule ? (
        <RateRuleFormDialog
          seasonId={seasonId}
          cardId={editingRule.card}
          open={!!editingRule}
          onOpenChange={(o) => !o && setEditingRule(null)}
          mode="edit"
          rule={editingRule}
          currencyCode={currencyCode}
          priceBasis={priceBasis}
          commission={commission}
          tax={tax}
        />
      ) : null}
      {deletingRule ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeletingRule(null)}
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
