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
import type { RateBand } from "@/features/properties/schemas";
import type { MatrixCell as CellModel } from "../matrixModel";

interface MatrixCellProps {
  cell: CellModel;
  currencyCode: string | null;
  canWrite: boolean;
  /** Commit an inline nightly-price edit (optimistic). */
  onCommitNightly: (bandId: number, nightly: string) => void;
  /** Open the full band dialog (party bands, weekly, POA). */
  onEditBand: (band: RateBand) => void;
  /** Open the create dialog seeded with this empty cell's segment + band. */
  onFill: (cell: CellModel) => void;
  onDeleteBand: (band: RateBand) => void;
}

/**
 * One matrix intersection: an empty (fillable) coordinate, a POA-masked rule, or
 * a priced rule with an inline nightly editor. Weekly/party/POA and deletion go
 * through the rule dialog + confirm — the inline path only fast-edits nightly.
 */
export function MatrixCell({
  cell,
  currencyCode,
  canWrite,
  onCommitNightly,
  onEditBand,
  onFill,
  onDeleteBand,
}: MatrixCellProps) {
  const { t } = useTranslation("properties");
  const band = cell.band;
  const [draft, setDraft] = useState(band?.nightly ?? "");

  // Keep the input in sync when the underlying band changes (optimistic write,
  // refetch, or a different card selected reusing this cell position).
  useEffect(() => {
    setDraft(band?.nightly ?? "");
  }, [band?.nightly, band?.id]);

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

  const commit = () => {
    const next = draft.trim();
    // Empty or unchanged → no write (clearing a price / setting POA is a
    // structural edit that must go through the dialog, which nulls both prices).
    if (!next || next === (band.nightly ?? "")) {
      setDraft(band.nightly ?? "");
      return;
    }
    onCommitNightly(band.id, next);
  };

  return (
    <div className="flex items-center gap-1">
      <MoneyInput
        adornment={currencyAdornment(currencyCode)}
        value={draft}
        inputMode="decimal"
        aria-label={t("rate_workbench.matrix.nightly_for", {
          from: cell.dateFrom,
          to: cell.dateTo,
        })}
        className="h-8"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          } else if (e.key === "Escape") {
            setDraft(band.nightly ?? "");
            e.currentTarget.blur();
          }
        }}
        disabled={!canWrite}
      />
      {menu}
    </div>
  );
}
