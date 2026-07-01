import { isNonNegativeMoney, isPositiveMoney, parseMoney } from "@/lib/format/money";
import type { StagedBand, StagedLine } from "./schemas";

// The bands on a banded line that will actually become saved quotation lines:
// checked, non-POA and with a real total. POA / unchecked / no-total bands are
// display-only and never expand into a saved line (GAP-044).
export function checkedSaveableBands(line: StagedLine): StagedBand[] {
  return line.occupancy_bands?.filter((b) => b.checked && !b.is_poa && b.total != null) ?? [];
}

// The net total a staged line contributes to the shortlist. Replicates the server's
// `QuotationService.price_line`: a manual line uses the operator-typed total; a
// priced line nets its discount off the engine gross and is floored at zero (a
// discount larger than the gross renders 0, never negative).
//
// Returns null when the figure can't be computed — no engine total yet, or a
// blank/non-numeric manual total — so callers render "—" and exclude the line
// from the subtotal rather than poisoning it with NaN.
export function lineEffectiveTotal(line: StagedLine): number | null {
  // A banded villa is a list of alternatives, not one price — it contributes no
  // single figure to the subtotal; the shortlist renders the band rows instead.
  if (line.occupancy_bands != null) return null;
  if (line.is_manual) {
    const total = parseMoney(line.total);
    return Number.isFinite(total) ? total : null;
  }
  const gross = parseMoney(line.total);
  if (!Number.isFinite(gross)) return null;
  const discount = parseMoney(line.discount);
  const net = gross - (Number.isFinite(discount) ? discount : 0);
  return Math.max(net, 0);
}

// Per-field validity for a staged line, keyed by i18n message so the shortlist can
// surface inline errors AND gate Save from one definition. The single source of
// truth for staged-line validation — mirrors the server's rules so the shortlist
// blocks before the parallel line-POST fan-out rather than 400-ing mid-flight:
//   - a discount, when present, must parse to a non-negative amount (closes the
//     "garbage discount POSTed → 400" hole);
//   - a manual line needs a total > 0 and a non-blank reason;
//   - a priced (non-manual) line must have a usable engine total, otherwise it
//     would be saved contributing nothing to the subtotal — the operator must
//     supply a manual override instead.
export interface StagedLineErrors {
  discount?: string;
  total?: string;
  reason?: string;
}

export function stagedLineErrors(line: StagedLine): StagedLineErrors {
  const errors: StagedLineErrors = {};
  // A banded line has no single total, no discount and no manual path — the only
  // way it's invalid is if the operator un-checked every non-POA band, which
  // would expand to zero saved lines.
  if (line.occupancy_bands != null) {
    if (checkedSaveableBands(line).length === 0) {
      errors.total = "quotations:schema_errors.bands_none_checked";
    }
    return errors;
  }
  if (line.discount.trim() !== "" && !isNonNegativeMoney(line.discount)) {
    errors.discount = "quotations:schema_errors.discount_invalid";
  }
  if (line.is_manual) {
    if (!isPositiveMoney(line.total)) {
      errors.total = "quotations:schema_errors.manual_total_required";
    }
    if (line.price_override_reason.trim().length === 0) {
      errors.reason = "quotations:schema_errors.override_reason_required";
    }
  } else if (lineEffectiveTotal(line) == null) {
    errors.total = "quotations:schema_errors.line_total_missing";
  }
  return errors;
}

export function isStagedLineValid(line: StagedLine): boolean {
  return Object.keys(stagedLineErrors(line)).length === 0;
}
