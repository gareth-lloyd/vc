import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Section } from "@/components/data/Section";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Card } from "@/components/ui/card";
import { todayIso } from "@/lib/format/date";
import { useArrivalsToday } from "../hooks";

const MAX_ROWS = 8;

export function ArrivalsList() {
  const { t } = useTranslation("dashboard");
  const { data, isLoading, isError } = useArrivalsToday();

  const today = todayIso();
  const viewAllHref = `/bookings?check_in_after=${today}&check_in_before=${today}&exclude_terminal=true`;

  return (
    <Section
      title={t("sections.arrivals_today")}
      actions={
        <Link to={viewAllHref} className="text-primary text-sm hover:underline">
          {t("sections.view_all")}
        </Link>
      }
    >
      {isError ? (
        <ErrorState description={t("errors.card")} />
      ) : isLoading ? (
        <SkeletonRows />
      ) : !data || data.results.length === 0 ? (
        <EmptyState title={t("empty.arrivals_today")} />
      ) : (
        <Card className="gap-0 py-0">
          <ul className="divide-border divide-y">
            {data.results.slice(0, MAX_ROWS).map((row) => (
              <li key={row.id}>
                <Link
                  to={`/bookings/${row.id}/overview`}
                  className="hover:bg-muted/40 flex items-center justify-between gap-3 px-5 py-3"
                >
                  <div className="min-w-0">
                    <div className="text-foreground truncate text-sm font-medium">
                      {row.property_name ?? `#${row.property}`}
                    </div>
                    <div className="text-muted-foreground truncate text-xs">
                      {row.guest_name ?? row.reference}
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

function SkeletonRows() {
  return (
    <Card className="gap-0 py-0">
      <ul className="divide-border divide-y">
        {[0, 1, 2].map((i) => (
          <li key={i} className="px-5 py-3">
            <div className="bg-muted h-4 w-40 animate-pulse rounded" />
            <div className="bg-muted mt-2 h-3 w-24 animate-pulse rounded" />
          </li>
        ))}
      </ul>
    </Card>
  );
}
