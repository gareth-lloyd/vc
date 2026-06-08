import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatMoney, parseMoney } from "@/lib/format/money";
import type { QuotationDetail } from "@/features/quotations/schemas";

// A quotation's lines are alternative *options*, not a basket — so the headline
// figure is the price range across them (min–max), never a sum.
function priceRange(quote: QuotationDetail, noPrice: string): string {
  const totals = quote.lines
    .map((line) => parseMoney(line.total))
    .filter((n) => Number.isFinite(n));
  if (totals.length === 0) return noPrice;
  const min = Math.min(...totals);
  const max = Math.max(...totals);
  return min === max
    ? formatMoney(min, quote.currency)
    : `${formatMoney(min, quote.currency)} – ${formatMoney(max, quote.currency)}`;
}

function QuoteCard({ quote }: { quote: QuotationDetail }) {
  const { t } = useTranslation("enquiries");
  return (
    <li className="border-border flex items-center justify-between gap-4 rounded-md border p-3">
      <div className="space-y-1">
        <Link
          to={`/quotations/${quote.id}`}
          className="text-foreground font-mono text-sm font-medium hover:underline"
          aria-label={t("quotes_section.view_aria", { reference: quote.reference })}
        >
          {quote.reference}
        </Link>
        <p className="text-muted-foreground text-xs">
          {t("quotes_section.options", { count: quote.lines.length })}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-foreground text-sm tabular-nums">
          {priceRange(quote, t("quotes_section.no_price"))}
        </span>
        <StatusBadge status={quote.status} />
      </div>
    </li>
  );
}

export function EnquiryQuoteStack({ quotations }: { quotations: QuotationDetail[] }) {
  const { t } = useTranslation("enquiries");

  if (quotations.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("quotes_section.empty")}</p>;
  }

  return (
    <ul className="space-y-2">
      {quotations.map((quote) => (
        <QuoteCard key={quote.id} quote={quote} />
      ))}
    </ul>
  );
}
