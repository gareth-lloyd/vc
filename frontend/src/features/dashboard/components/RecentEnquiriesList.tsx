import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Section } from "@/components/data/Section";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/format/date";
import type { EnquiryListItem } from "@/features/enquiries/schemas";
import { useRecentEnquiries } from "../hooks";

const MAX_ROWS = 5;

export function RecentEnquiriesList() {
  const { t } = useTranslation("dashboard");
  const { data, isLoading, isError } = useRecentEnquiries();

  return (
    <Section
      title={t("sections.recent_enquiries")}
      actions={
        <Link to="/enquiries" className="text-primary text-sm hover:underline">
          {t("sections.view_all")}
        </Link>
      }
    >
      {isError ? (
        <ErrorState description={t("errors.card")} />
      ) : isLoading ? (
        <SkeletonRows />
      ) : !data || data.results.length === 0 ? (
        <EmptyState title={t("empty.recent_enquiries")} />
      ) : (
        <Card className="gap-0 py-0">
          <ul className="divide-border divide-y">
            {data.results.slice(0, MAX_ROWS).map((row) => (
              <li key={row.id}>
                <Link
                  to={`/enquiries/${row.id}`}
                  className="hover:bg-muted/40 flex items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="min-w-0">
                    <div className="text-foreground truncate text-sm font-medium">
                      {nameOf(row)}
                    </div>
                    <div className="text-muted-foreground truncate text-xs">
                      {partyAndDates(row, t)}
                    </div>
                  </div>
                  <div className="text-muted-foreground shrink-0 font-mono text-xs">
                    {row.reference}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </Section>
  );
}

// Never fall back to the reference — it's already rendered alongside.
function nameOf(row: EnquiryListItem): string {
  const full = `${row.first_name} ${row.last_name}`.trim();
  return row.guest_name || full || row.email || "—";
}

function partyAndDates(
  row: EnquiryListItem,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const party = t("rows.guest_party", { count: row.adults });
  const children = row.children > 0 ? `, ${t("rows.with_children", { count: row.children })}` : "";
  const dates =
    row.date_from && row.date_to
      ? t("rows.dates_range", { from: formatDate(row.date_from), to: formatDate(row.date_to) })
      : t("rows.dates_unknown");
  return `${party}${children} · ${dates}`;
}

function SkeletonRows() {
  return (
    <Card className="gap-0 py-0">
      <ul className="divide-border divide-y">
        {[0, 1, 2].map((i) => (
          <li key={i} className="px-5 py-3">
            <div className="bg-muted h-4 w-44 animate-pulse rounded" />
            <div className="bg-muted mt-2 h-3 w-32 animate-pulse rounded" />
          </li>
        ))}
      </ul>
    </Card>
  );
}
