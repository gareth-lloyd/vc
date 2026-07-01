import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { formatMoney } from "@/lib/format/money";
import type { PriceQuote } from "../schemas";

interface QuoteResultCardProps {
  quote: PriceQuote;
  /** Resolved "Season · Period" label for the winning period, when known. */
  periodLabel?: string | null;
}

const nonZero = (value: string | undefined): boolean => !!value && Number(value) !== 0;

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground text-right tabular-nums">{children}</span>
    </div>
  );
}

/**
 * Guest-side quote breakdown. Shows the guest total and its components (rate,
 * inclusions, opt-in extras, discount) — but deliberately NOT owner economics
 * (net_to_owner / commission / tax): the engine mis-prices those for GROSS
 * plans (BUG-009), so we mark them pending rather than headline a wrong number.
 */
export function QuoteResultCard({ quote, periodLabel }: QuoteResultCardProps) {
  const { t } = useTranslation("properties");
  const currency = quote.currency_code ?? null;
  const nights = quote.lines.length;
  const inclusions = (quote.inclusion ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

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
        <div className="border-border mt-1 border-t pt-2">
          <Line label={t("rate_workbench.probe.result.guest_total")}>
            <span className="text-base font-semibold">
              {formatMoney(quote.total ?? "0", currency)}
            </span>
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
                <span>{ex.name}</span>
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

      {/* BUG-009: owner economics are unreliable for GROSS plans — surfaced as a
          pending note, never a figure. */}
      <p className="text-muted-foreground border-border border-t pt-2 text-xs italic">
        {t("rate_workbench.probe.result.owner_pending")}
      </p>
    </div>
  );
}
