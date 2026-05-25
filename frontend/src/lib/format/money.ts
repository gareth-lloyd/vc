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
  return Number(trimmed);
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
