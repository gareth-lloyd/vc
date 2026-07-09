import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { formatMoney, parseMoney } from "@/lib/format/money";
import type { PriceQuote } from "../schemas";

interface QuoteResultCardProps {
  quote: PriceQuote;
  /** Resolved "Season · Period" label for the winning period, when known. */
  periodLabel?: string | null;
}

const nonZero = (value: string | undefined): boolean => !!value && Number(value) !== 0;

/** parseMoney, but a missing/blank amount reads as 0 rather than NaN. */
const money = (value: string | null | undefined): number => {
  const n = parseMoney(value ?? "");
  return Number.isNaN(n) ? 0 : n;
};

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground text-right tabular-nums">{children}</span>
    </div>
  );
}

/**
 * Guest-side quote breakdown plus owner economics. The engine's `total` is
 * `price_basis`-aware (BUG-009): the guest figure for GROSS (commission+tax
 * carved out of the rate) and NET (grossed up) alike, so it is trusted as the
 * headline. Owner economics (net_to_owner / commission / tax) render in their
 * own section when the response carries them.
 */
export function QuoteResultCard({ quote, periodLabel }: QuoteResultCardProps) {
  const { t } = useTranslation("properties");
  const currency = quote.currency_code ?? null;
  const nights = quote.lines.length;
  const inclusions = (quote.inclusion ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  const lineSum = money(quote.rate_subtotal) + money(quote.extras_total) - money(quote.discount);
  // Trust the engine total; fall back to the reconciled line sum only when a
  // (schema-optional) `total` is missing or unparseable — never headline £0.00.
  const totalNum = parseMoney(quote.total ?? "");
  const guestTotal = Number.isNaN(totalNum) ? lineSum : totalNum;
  // "Taxes & fees" is the NET gross-up the guest pays on top of the owner net,
  // taken from the engine's own commission+tax figures rather than re-derived
  // by subtracting money (the same money renders owner-side below, under its
  // explicit labels). GROSS plans carry commission+tax inside the rate — no
  // additive guest line. Responses predating `price_basis` fall back to the
  // total-over-lines gap.
  const componentSum = money(quote.commission) + money(quote.tax);
  const hasComponents = quote.commission != null || quote.tax != null;
  const taxesFees =
    quote.price_basis === "gross"
      ? 0
      : quote.price_basis === "net" && hasComponents
        ? componentSum
        : guestTotal - lineSum;
  const showTaxesFees = taxesFees > 0.005;

  const hasOwnerEconomics =
    quote.net_to_owner != null || quote.commission != null || quote.tax != null;

  return (
    <div className="border-border bg-card shadow-card space-y-4 rounded-lg border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-foreground text-sm font-semibold">
          {periodLabel ?? t("rate_workbench.probe.result.winning_default")}
        </span>
        {quote.is_projected ? (
          <Badge variant="outline">{t("rate_workbench.probe.result.projected")}</Badge>
        ) : null}
        {quote.occupancy_pricing ? (
          <Badge variant="secondary">{t("rate_workbench.probe.result.occupancy_priced")}</Badge>
        ) : null}
      </div>

      <dl className="space-y-1 text-sm">
        <Line label={t("rate_workbench.probe.result.nights", { count: nights })}>
          {formatMoney(quote.rate_subtotal ?? "0", currency)}
        </Line>
        {nonZero(quote.extras_total) ? (
          <Line label={t("rate_workbench.probe.result.extras")}>
            {formatMoney(quote.extras_total ?? "0", currency)}
          </Line>
        ) : null}
        {nonZero(quote.discount) ? (
          <Line label={t("rate_workbench.probe.result.discount")}>
            −{formatMoney(quote.discount ?? "0", currency)}
          </Line>
        ) : null}
        {showTaxesFees ? (
          <Line label={t("rate_workbench.probe.result.taxes_fees")}>
            {formatMoney(taxesFees, currency)}
          </Line>
        ) : null}
        <div className="border-border mt-1 border-t pt-2">
          <Line label={t("rate_workbench.probe.result.guest_total")}>
            <span className="text-base font-semibold">{formatMoney(guestTotal, currency)}</span>
          </Line>
        </div>
      </dl>

      {quote.extras.length > 0 ? (
        <div className="space-y-1">
          <p className="text-muted-foreground text-xs font-medium">
            {t("rate_workbench.probe.result.extras_heading")}
          </p>
          <ul className="text-muted-foreground space-y-0.5 text-xs">
            {quote.extras.map((ex) => (
              <li key={ex.extra_id} className="flex justify-between gap-4">
                <span className="flex items-baseline gap-1.5">
                  {ex.name}
                  {ex.commissionable === false ? (
                    <span className="text-muted-foreground/70 italic">
                      {t("rate_workbench.probe.result.non_commissionable")}
                    </span>
                  ) : null}
                </span>
                <span className="tabular-nums">{formatMoney(ex.computed_amount, currency)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {inclusions.length > 0 ? (
        <div className="space-y-1">
          <p className="text-muted-foreground text-xs font-medium">
            {t("rate_workbench.probe.result.included_heading")}
          </p>
          <ul className="text-muted-foreground list-inside list-disc space-y-0.5 text-xs">
            {inclusions.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {quote.changeover_shifted_from ? (
        <p className="text-muted-foreground text-xs">
          {t("rate_workbench.probe.result.changeover_shifted", {
            from: quote.changeover_shifted_from,
          })}
        </p>
      ) : null}

      {hasOwnerEconomics ? (
        <div className="border-border space-y-1 border-t pt-2">
          <p className="text-muted-foreground text-xs font-medium">
            {t("rate_workbench.probe.result.owner_heading")}
          </p>
          <dl className="space-y-1 text-sm">
            {quote.net_to_owner != null ? (
              <Line label={t("rate_workbench.probe.result.net_to_owner")}>
                {formatMoney(quote.net_to_owner, currency)}
              </Line>
            ) : null}
            {quote.commission != null ? (
              <Line label={t("rate_workbench.probe.result.commission")}>
                {formatMoney(quote.commission, currency)}
              </Line>
            ) : null}
            {quote.tax != null ? (
              <Line label={t("rate_workbench.probe.result.tax")}>
                {formatMoney(quote.tax, currency)}
              </Line>
            ) : null}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
