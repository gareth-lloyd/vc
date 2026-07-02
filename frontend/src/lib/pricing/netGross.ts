/**
 * Net↔gross rate-entry derivation (GAP-035).
 *
 * Owners quote rates as either net (what they receive) or gross (what the guest
 * pays). Staff type one figure and pick the basis; this derives the counterpart
 * *for display only* — the canonical stored figure is always exactly what was
 * typed, plus the plan's `price_basis`. Persisting the derived side would
 * double-count against the engine's basis-aware carve-out at quote time.
 *
 * The math mirrors the pricing engine's mode-aware steps 8-9
 * (`django_res_design/04-pricing.md`, legacy `RatesModel.Calculate()`;
 * implemented by BUG-009 — `PricingEngine._derive_commission_and_tax`, same
 * quantization order: the raw commission feeds the tax base, rounding at the
 * end), so a band entered here prices identically at quote time. The math:
 *
 *   GROSS (typed = guest gross) → derive owner net, by carving out:
 *     tax        = gross × taxPct/100                  (0 when exempt)
 *     commission = (gross − tax) × commPct/100         (percentage)
 *                = the flat amount                      (fixed)
 *     net_to_owner = gross − tax − commission
 *
 *   NET (typed = owner net) → derive guest total, by grossing up:
 *     commission = net/(1 − commPct/100) − net         (percentage)
 *                = the flat amount                      (fixed)
 *     tax        = (net + commission)/(1 − taxPct/100) − (net + commission)
 *     total      = net + commission + tax
 *
 * Note a *percentage* commission of 20% means "20% of the gross", so the
 * gross-up divides by 0.8 (×1.25) — not ×1.2. A *fixed* commission is the flat
 * amount in both directions.
 */

import { parseMoney } from "@/lib/format/money";

export type PriceBasis = "net" | "gross";

const PRICE_BASES: readonly PriceBasis[] = ["net", "gross"];

/**
 * Narrow a loose basis string (e.g. the settings endpoint's free-string
 * `prices_entered_as_effective`) to a valid {@link PriceBasis}, falling back to
 * GROSS — the safe reconciling default for legacy data.
 */
export function asPriceBasis(value: string | null | undefined): PriceBasis {
  return PRICE_BASES.includes((value ?? "") as PriceBasis) ? (value as PriceBasis) : "gross";
}

// Fields are optional/nullable to accept the API's read shape verbatim (the
// settings endpoint's `commission` / `tax` objects) without a mapping step.
export interface CommissionInput {
  /** `"percent"` | `"fixed"` (or null when no finance is configured). */
  calculation_type?: string | null;
  /** Decimal string: a percentage when `percent`, an absolute amount when `fixed`. */
  amount?: string | null;
}

export interface TaxInput {
  /** Decimal-string percentage, e.g. `"13.00"`. */
  percentage?: string | null;
  /** When true (or the policy is missing) tax is skipped entirely. */
  is_exempt?: boolean | null;
}

export interface DerivedCounterpart {
  /** The derived figure: owner net for a GROSS basis, guest total for a NET basis. */
  counterpart: number;
  /** Commission component of the derivation. */
  commission: number;
  /** Tax component of the derivation (0 when exempt or no tax rate). */
  tax: number;
}

/** Banker's rounding (ROUND_HALF_EVEN) to `dp` places — matches the backend
 * `quantise_money()` policy so the displayed figure agrees with the engine.
 * Computes on the magnitude then reapplies the sign so negatives round
 * symmetrically. */
export function roundHalfEven(value: number, dp = 2): number {
  if (!Number.isFinite(value)) return value;
  const sign = value < 0 ? -1 : 1;
  const factor = 10 ** dp;
  const scaled = Math.abs(value) * factor;
  const floor = Math.floor(scaled);
  const frac = scaled - floor;
  const HALF_EPS = 1e-8;
  let unit: number;
  if (Math.abs(frac - 0.5) < HALF_EPS) {
    // Exact halfway (modulo binary-float noise) → round to the even neighbour.
    unit = floor % 2 === 0 ? floor : floor + 1;
  } else {
    unit = Math.round(scaled);
  }
  return (sign * unit) / factor;
}

function pct(value: string | null | undefined): number {
  const parsed = parseMoney(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Derive the net/gross counterpart of `amount` for display, or `null` when
 * there is nothing meaningful to derive (no/zero/unparseable amount — e.g. a
 * POA-masked or empty input) or the inputs are degenerate (a percentage ≥ 100%
 * would divide by zero or flip sign on the gross-up).
 */
export function deriveNetGross(
  amount: string | number | null | undefined,
  basis: PriceBasis,
  commission: CommissionInput | null,
  tax: TaxInput | null,
  dp = 2,
): DerivedCounterpart | null {
  const base = parseMoney(amount);
  if (!Number.isFinite(base) || base <= 0) return null;

  const isFixed = commission?.calculation_type === "fixed";
  const fixedCommission = isFixed ? pct(commission?.amount ?? null) : null;
  const commissionPct = commission?.calculation_type === "percent" ? pct(commission.amount) : 0;
  const taxPct = tax && tax.is_exempt !== true ? pct(tax.percentage) : 0;

  let commissionAmt: number;
  let taxAmt: number;
  let counterpart: number;

  if (basis === "gross") {
    // Carve commission + tax out of the gross to reveal the owner net.
    taxAmt = (base * taxPct) / 100;
    commissionAmt =
      fixedCommission != null ? fixedCommission : ((base - taxAmt) * commissionPct) / 100;
    counterpart = base - taxAmt - commissionAmt;
  } else {
    // Gross up the owner net to the guest total.
    if (fixedCommission != null) {
      commissionAmt = fixedCommission;
    } else {
      if (commissionPct >= 100) return null;
      commissionAmt = base / (1 - commissionPct / 100) - base;
    }
    const taxBase = base + commissionAmt;
    if (taxPct >= 100) return null;
    taxAmt = taxPct ? taxBase / (1 - taxPct / 100) - taxBase : 0;
    counterpart = base + commissionAmt + taxAmt;
  }

  // Degenerate: commission/tax exceed the gross, so the owner net would be
  // negative — display nothing rather than a "-£200.00" owner-net (mirrors the
  // NET branch's null on a ≥100% gross-up).
  if (counterpart < 0) return null;

  return {
    counterpart: roundHalfEven(counterpart, dp),
    commission: roundHalfEven(commissionAmt, dp),
    tax: roundHalfEven(taxAmt, dp),
  };
}
