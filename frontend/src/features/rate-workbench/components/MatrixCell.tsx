import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoneyInput } from "@/components/ui/money-input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { currencyAdornment } from "@/lib/format/money";
import { MONEY_PATTERN, type RateBand } from "@/features/properties/schemas";
import { bandLabel } from "../matrixModel";
import type { MatrixCell as CellModel } from "../matrixModel";
import type { PriceField } from "../hooks";

interface MatrixCellProps {
  cell: CellModel;
  currencyCode: string | null;
  canWrite: boolean;
  /** Commit an inline nightly/weekly price edit (optimistic). */
  onCommitPrice: (bandId: number, field: PriceField, value: string) => void;
  /** Open the full band dialog (party bands, POA, clearing a price). */
  onEditBand: (band: RateBand) => void;
  /** Open the create dialog seeded with this empty cell's segment + band. */
  onFill: (cell: CellModel) => void;
  onDeleteBand: (band: RateBand) => void;
}

interface PriceRowProps {
  label: string;
  ariaLabel: string;
  adornment: string | null;
  /** The band's stored price for this field ("" when unset). */
  value: string;
  /** Resyncs the draft when a different band reuses this cell position. */
  bandId: number;
  disabled: boolean;
  onCommit: (value: string) => void;
}

/**
 * One labelled inline price editor (module scope — defining it inside
 * `MatrixCell` would give it a new identity every render and remount the
 * input, dropping focus/caret mid-edit).
 */
function PriceRow({
  label,
  ariaLabel,
  adornment,
  value,
  bandId,
  disabled,
  onCommit,
}: PriceRowProps) {
  const [draft, setDraft] = useState(value);

  // Keep the input in sync when the underlying band changes (optimistic write,
  // refetch, or a different band selected reusing this cell position).
  useEffect(() => {
    setDraft(value);
  }, [value, bandId]);

  const reset = () => setDraft(value);
  const commit = () => {
    const next = draft.trim();
    // Empty or unchanged → no write (clearing a price / setting POA is a
    // structural edit that must go through the dialog, which nulls both prices).
    // A malformed draft resets too — shipping it would only 400 and roll back.
    if (!next || next === value || !MONEY_PATTERN.test(next)) {
      reset();
      return;
    }
    onCommit(next);
  };

  return (
    <div className="flex items-center gap-1">
      <span aria-hidden="true" className="text-muted-foreground w-9 shrink-0 text-[10px]">
        {label}
      </span>
      <MoneyInput
        adornment={adornment}
        value={draft}
        inputMode="decimal"
        aria-label={ariaLabel}
        className="h-8"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          } else if (e.key === "Escape") {
            reset();
            e.currentTarget.blur();
          }
        }}
        disabled={disabled}
      />
    </div>
  );
}

/**
 * One matrix intersection: an empty (fillable) coordinate, a POA-masked rule, or
 * a priced rule with stacked inline nightly + weekly editors. Party/POA/clearing
 * a price and deletion go through the rule dialog + confirm — the inline path
 * only fast-edits prices.
 */
export function MatrixCell({
  cell,
  currencyCode,
  canWrite,
  onCommitPrice,
  onEditBand,
  onFill,
  onDeleteBand,
}: MatrixCellProps) {
  const { t } = useTranslation("properties");
  const band = cell.band;

  if (!band) {
    const dash = (
      <span className="text-muted-foreground/40 block text-center text-xs">
        {t("common.unset")}
      </span>
    );
    if (!canWrite) return dash;
    // A different band's rule already covers this dates×party region — a create
    // here would 4xx on the overlap constraint, so offer no "+" (just explain).
    if (!cell.fillable) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block w-full">{dash}</span>
          </TooltipTrigger>
          <TooltipContent>{t("rate_workbench.matrix.covered")}</TooltipContent>
        </Tooltip>
      );
    }
    return (
      <Button
        variant="ghost"
        size="icon"
        className="text-muted-foreground/60 h-8 w-full"
        aria-label={t("rate_workbench.matrix.fill_cell")}
        onClick={() => onFill(cell)}
      >
        <Plus className="h-3.5 w-3.5" />
      </Button>
    );
  }

  const menu = canWrite ? (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 shrink-0 px-1"
          aria-label={t("rate_workbench.matrix.cell_menu")}
        >
          ···
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => onEditBand(band)}>
          {t("rate_workbench.matrix.edit_rule")}
        </DropdownMenuItem>
        <DropdownMenuItem className="text-destructive" onClick={() => onDeleteBand(band)}>
          {t("rate_workbench.matrix.delete_rule")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  ) : null;

  if (band.is_poa) {
    return (
      <div className="flex items-center justify-between gap-1">
        <Badge variant="outline">{t("rate_workbench.matrix.poa")}</Badge>
        {menu}
      </div>
    );
  }

  // Distinguishes this cell's inputs from the same period's other bands (whose
  // aria-labels share the dates) — the band's own range, not the column's.
  const partyLabel = bandLabel({
    minParty: band.min_party ?? null,
    maxParty: band.max_party ?? null,
  });
  const party =
    partyLabel != null
      ? t("rate_workbench.matrix.party_pax", { range: partyLabel })
      : t("rate_workbench.matrix.any_party");
  const adornment = currencyAdornment(currencyCode);

  return (
    <div className="flex items-start gap-1">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <PriceRow
          label={t("rate_workbench.matrix.nightly_short")}
          ariaLabel={t("rate_workbench.matrix.nightly_for", {
            from: cell.dateFrom,
            to: cell.dateTo,
            party,
          })}
          adornment={adornment}
          value={band.nightly ?? ""}
          bandId={band.id}
          disabled={!canWrite}
          onCommit={(value) => onCommitPrice(band.id, "nightly", value)}
        />
        <PriceRow
          label={t("rate_workbench.matrix.weekly_short")}
          ariaLabel={t("rate_workbench.matrix.weekly_for", {
            from: cell.dateFrom,
            to: cell.dateTo,
            party,
          })}
          adornment={adornment}
          value={band.weekly ?? ""}
          bandId={band.id}
          disabled={!canWrite}
          onCommit={(value) => onCommitPrice(band.id, "weekly", value)}
        />
      </div>
      {menu}
    </div>
  );
}
