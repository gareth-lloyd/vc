import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { bandDateRangeLabel, bandTitle, type WorkbenchBand } from "../toLanes";

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <dt>{term}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

/** Contextual detail shown in a band's popover — the primary read affordance at year scale. */
export function BandDetail({
  band,
  showGapAction = false,
}: {
  band: WorkbenchBand;
  /** Coverage gaps, writers only: append the "add a period" call to action. */
  showGapAction?: boolean;
}) {
  const { t } = useTranslation("properties");
  const meta = band.meta;
  const currency = meta.currencyCode ?? null;

  const title = bandTitle(band, t);

  // Shared by the (effective) price row and the Q-018 "reduced from" base row.
  const priceRange = (min: number, max: number | null | undefined) =>
    min === max
      ? formatMoney(String(min), currency)
      : `${formatMoney(String(min), currency)} – ${formatMoney(String(max), currency)}`;

  return (
    <div className="space-y-2 text-sm">
      <p className="text-foreground font-medium">{title}</p>
      <dl className="text-muted-foreground space-y-1">
        <Row term={t("rate_workbench.detail.dates")}>{bandDateRangeLabel(band, t)}</Row>

        {meta.isGap || (band.laneKey === "rates" && meta.noRates) ? (
          <Row term={t("rate_workbench.detail.plan")}>{meta.planName}</Row>
        ) : null}

        {band.laneKey === "rates" && (meta.minPrice != null || meta.hasPoa) ? (
          <>
            {meta.minPrice != null ? (
              <Row term={t("rate_workbench.detail.price_range")}>
                {priceRange(meta.minPrice, meta.maxPrice)}
              </Row>
            ) : null}
            {/* Q-018: the price above is the EFFECTIVE one; surface the base
                it was reduced from, plus the audit trail when recorded. */}
            {meta.hasReduction && meta.baseMinPrice != null ? (
              <Row term={t("rate_workbench.detail.reduced_from")}>
                {priceRange(meta.baseMinPrice, meta.baseMaxPrice)}
              </Row>
            ) : null}
            {meta.hasReduction && meta.reductionReason ? (
              <Row term={t("rate_workbench.detail.reduction_reason")}>{meta.reductionReason}</Row>
            ) : null}
            {meta.hasReduction && meta.reducedAt ? (
              <Row term={t("rate_workbench.detail.reduced_on")}>{formatDate(meta.reducedAt)}</Row>
            ) : null}
            {meta.hasPoa ? (
              <Row term={t("rate_workbench.detail.poa")}>
                <Check className="text-success inline h-4 w-4" aria-hidden />
              </Row>
            ) : null}
            <Row term={t("rate_workbench.detail.plan")}>{meta.planName}</Row>
          </>
        ) : null}

        {band.laneKey === "extras" ? (
          <>
            <Row term={t("rate_workbench.detail.required")}>
              {meta.isMandatory
                ? t("rate_workbench.detail.mandatory")
                : t("rate_workbench.detail.optional")}
            </Row>
            {meta.amount != null ? (
              <Row term={t("rate_workbench.detail.amount")}>
                {formatMoney(meta.amount, currency)}
              </Row>
            ) : null}
          </>
        ) : null}

        {band.laneKey === "discounts" ? (
          <>
            {meta.code ? (
              <Row term={t("rate_workbench.detail.code")}>
                <span className="font-mono text-xs">{meta.code}</span>
              </Row>
            ) : null}
            {meta.kind ? <Row term={t("rate_workbench.detail.kind")}>{meta.kind}</Row> : null}
            {/* Amount is basis-ambiguous (percent vs fixed), so it's shown raw
                beside its kind — matching the Pricing tab's discounts table. */}
            {meta.amount != null ? (
              <Row term={t("rate_workbench.detail.amount")}>{meta.amount}</Row>
            ) : null}
          </>
        ) : null}

        {band.laneKey === "inclusions" && meta.copy ? (
          <Row term={t("rate_workbench.detail.copy")}>
            <span className="line-clamp-3">{meta.copy}</span>
          </Row>
        ) : null}
      </dl>

      {band.laneKey === "rates" && meta.noRates ? (
        <p className="text-muted-foreground">{t("rate_workbench.detail.no_rates_yet")}</p>
      ) : null}
      {showGapAction ? (
        <p className="text-muted-foreground">{t("rate_workbench.coverage.gap_hint")}</p>
      ) : null}
    </div>
  );
}
