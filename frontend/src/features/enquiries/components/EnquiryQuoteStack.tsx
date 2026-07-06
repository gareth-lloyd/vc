import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatMoney, parseMoney } from "@/lib/format/money";
import { quotationStatusLabel, type QuotationDetail } from "@/lib/domain/quotation";

// A quotation's lines are alternative *options*, not a basket — so the headline
// figure is the price range across them (min–max), never a sum. Each line is
// priced in its own currency (GAP-014) and amounts in different currencies
// aren't comparable, so the range is computed PER currency (first-seen order)
// and joined — a mixed quote reads e.g. "£900.00 – £1,200.00 · €1,000.00".
function priceRange(quote: QuotationDetail, noPrice: string): string {
  const byCurrency = new Map<string | null, number[]>();
  for (const line of quote.lines) {
    const amount = parseMoney(line.total);
    if (!Number.isFinite(amount)) continue;
    const currency = line.currency ?? null;
    const amounts = byCurrency.get(currency) ?? [];
    amounts.push(amount);
    byCurrency.set(currency, amounts);
  }
  if (byCurrency.size === 0) return noPrice;
  return [...byCurrency.entries()]
    .map(([currency, amounts]) => {
      const min = Math.min(...amounts);
      const max = Math.max(...amounts);
      return min === max
        ? formatMoney(min, currency)
        : `${formatMoney(min, currency)} – ${formatMoney(max, currency)}`;
    })
    .join(" · ");
}

function QuoteCard({ quote }: { quote: QuotationDetail }) {
  const { t } = useTranslation("enquiries");
  return (
    <li className="border-border flex items-center justify-between gap-4 rounded-md border p-3">
      <div className="space-y-1">
        <Link
          to={`/enquiries/quotes/${quote.id}`}
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
        <StatusBadge status={quote.status} label={quotationStatusLabel(quote.status)} />
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
