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

// True when `value` parses to a finite money amount strictly greater than zero
// — e.g. a manual line's total. Pure (no schema import), so schemas.ts and the
// cart can share one definition without an import cycle.
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

export function formatMoney(
  value: string | number | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (value == null || !currencyCode) return "—";
  const amount = parseMoney(value);
  if (!Number.isFinite(amount)) return "—";
  const code = currencyCode.toUpperCase();
  const formatted = amount.toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const symbol = SYMBOLS[code];
  return symbol ? `${symbol}${formatted}` : `${formatted} ${code}`;
}
