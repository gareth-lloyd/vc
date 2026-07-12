const SYMBOLS: Record<string, string> = {
  GBP: "£",
  EUR: "€",
  USD: "$",
  AUD: "A$",
  CAD: "C$",
  CHF: "CHF ",
  JPY: "¥",
};

export function parseMoney(value: string | number | null | undefined): number {
  if (value == null) return Number.NaN;
  if (typeof value === "number") return value;
  const trimmed = value.trim();
  if (!trimmed) return Number.NaN;
  // All money is displayed en-GB (`formatMoney` is locale-pinned), so input
  // mirrors that: accept commas ONLY in valid thousands-grouping positions
  // ("1,234,567.89") and strip them. Reject any other comma as NaN rather than
  // silently mis-parsing it — this is deliberately strict so a decimal-comma
  // typed by an `el`/Greek operator ("1000,50") is rejected loudly instead of
  // becoming 100050. API decimal strings ("1234.50") have no comma and fall
  // straight through.
  if (trimmed.includes(",")) {
    if (!/^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(trimmed)) return Number.NaN;
    return Number(trimmed.replace(/,/g, ""));
  }
  return Number(trimmed);
}

// Normalise an operator-typed money string to a canonical 2-dp decimal for the
// wire (e.g. "1,000" → "1000.00"), or null when it doesn't parse to a finite
// number so callers can fall back. Matches the app's hardcoded 2-dp convention.
export function toDecimalString(value: string | number | null | undefined): string | null {
  const parsed = parseMoney(value);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : null;
}

// True when `value` parses to a finite money amount strictly greater than zero
// — e.g. a manual line's total. Pure (no schema import), so schemas.ts and the
// shortlist can share one definition without an import cycle.
export function isPositiveMoney(value: string | number | null | undefined): boolean {
  const parsed = parseMoney(value);
  return Number.isFinite(parsed) && parsed > 0;
}

// True when `value` parses to a finite money amount of zero or more — e.g. a
// per-line discount, which may be zero but never negative.
export function isNonNegativeMoney(value: string | number | null | undefined): boolean {
  const parsed = parseMoney(value);
  return Number.isFinite(parsed) && parsed >= 0;
}

// The token to render as a money-input adornment: the currency symbol when
// known (e.g. "£", "€"), else the uppercased code itself (e.g. "AED" for a
// currency with no mapped symbol), else `null` when no currency is resolved —
// callers show a "set currency" prompt in that case rather than a blank prefix.
export function currencyAdornment(currencyCode: string | null | undefined): string | null {
  if (!currencyCode) return null;
  const code = currencyCode.toUpperCase();
  return SYMBOLS[code]?.trim() ?? code;
}

// The symbol-or-code wrapper shared by every formatter: a known symbol hugs the
// number ("£1,234.56"), an unmapped code trails it ("1,234.56 AED"). Keeps the
// en-GB pinning + symbol map in one place.
function withCurrency(formatted: string, code: string): string {
  const symbol = SYMBOLS[code];
  return symbol ? `${symbol}${formatted}` : `${formatted} ${code}`;
}

export function formatMoney(
  value: string | number | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (value == null || !currencyCode) return "—";
  const amount = parseMoney(value);
  if (!Number.isFinite(amount)) return "—";
  return withCurrency(
    amount.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    currencyCode.toUpperCase(),
  );
}

// GAP-080: quote surfaces list lines priced in different base currencies side
// by side (GAP-014), where a bare symbol is ambiguous — so the ISO code is
// rendered explicitly for every currency ("£1,500.00 GBP"), not only unmapped
// ones. Skips the append when the mapped symbol already reads as the code
// (CHF), and never decorates the "—" fallback.
export function formatMoneyWithCode(
  value: string | number | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (value == null || !currencyCode) return "—";
  const formatted = formatMoney(value, currencyCode);
  if (formatted === "—") return formatted;
  const code = currencyCode.toUpperCase();
  const symbol = SYMBOLS[code];
  if (!symbol || symbol.trim() === code) return formatted;
  return `${formatted} ${code}`;
}

// Whole-amount headline figure for at-a-glance summaries (e.g. "from £20,378/wk")
// — drops the cents that add noise without precision at the guide-price altitude.
export function formatMoneyWhole(
  value: string | number | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (value == null || !currencyCode) return "—";
  const amount = parseMoney(value);
  if (!Number.isFinite(amount)) return "—";
  return withCurrency(
    Math.round(amount).toLocaleString("en-GB", { maximumFractionDigits: 0 }),
    currencyCode.toUpperCase(),
  );
}

// Compact notation ("£20.4K") for dense cells like the per-week price strip,
// where the full figure won't fit; callers surface the exact amount on hover.
export function formatMoneyCompact(
  value: string | number | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (value == null || !currencyCode) return "—";
  const amount = parseMoney(value);
  if (!Number.isFinite(amount)) return "—";
  return withCurrency(
    amount.toLocaleString("en-GB", { notation: "compact", maximumFractionDigits: 1 }),
    currencyCode.toUpperCase(),
  );
}
