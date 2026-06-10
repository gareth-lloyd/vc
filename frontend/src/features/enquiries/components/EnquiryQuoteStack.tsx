import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatMoney, parseMoney } from "@/lib/format/money";
import type { QuotationDetail } from "@/features/quotations/schemas";

// A quotation's lines are alternative *options*, not a basket — so the headline
// figure is the price range across them (min–max), never a sum. Each line is
// priced in its own currency (GAP-014), so the endpoints format with their own
// line's code — a mixed quote reads e.g. "£900.00 – €1,200.00".
function priceRange(quote: QuotationDetail, noPrice: string): string {
  const priced = quote.lines
    .map((line) => ({ amount: parseMoney(line.total), currency: line.currency ?? null }))
    .filter((p) => Number.isFinite(p.amount));
  if (priced.length === 0) return noPrice;
  let min = priced[0];
  let max = priced[0];
  for (const p of priced) {
    if (p.amount < min.amount) min = p;
    if (p.amount > max.amount) max = p;
  }
  const low = formatMoney(min.amount, min.currency);
  const high = formatMoney(max.amount, max.currency);
  return low === high ? low : `${low} – ${high}`;
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
