import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { todayIso } from "@/lib/format/date";
import { useArrivalsToday } from "../hooks";

const MAX_ROWS = 6;

export function HeroArrivals() {
  const { t } = useTranslation("dashboard");
  const today = todayIso();
  const { data, isLoading, isError } = useArrivalsToday();

  const viewAllHref = `/bookings?check_in_after=${today}&check_in_before=${today}&exclude_terminal=true`;
  const count = data?.count ?? 0;
  const rows = data?.results.slice(0, MAX_ROWS) ?? [];

  return (
    <article className="bg-card border-border shadow-card rounded-lg border">
      <div className="grid gap-8 p-6 md:grid-cols-[auto_1fr] md:p-8">
        <div className="flex flex-col gap-2">
          <span className="text-muted-foreground text-[11px] font-medium tracking-wider uppercase">
            {t("sections.arrivals_today")}
          </span>
          <span className="text-foreground text-6xl leading-none font-semibold tabular-nums md:text-7xl">
            {isError ? "—" : isLoading ? "·" : count}
          </span>
          <span className="text-muted-foreground max-w-[14ch] text-sm">
            {t("hero.arrivals_label")}
          </span>
          <Link
            to={viewAllHref}
            className="text-primary hover:text-brand-800 group mt-2 inline-flex items-center gap-1.5 text-sm font-medium"
          >
            {t("hero.view_schedule")}
            <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>

        <div className="border-border md:border-l md:pl-8">
          {isError ? (
            <ErrorState description={t("errors.card")} />
          ) : isLoading ? (
            <SkeletonRows />
          ) : rows.length === 0 ? (
            <div className="bg-muted/50 flex h-full min-h-[14rem] items-center justify-center rounded-lg">
              <EmptyState title={t("empty.arrivals_today")} />
            </div>
          ) : (
            <ul className="divide-border divide-y">
              {rows.map((row) => (
                <li key={row.id}>
                  <Link
                    to={`/bookings/${row.id}/overview`}
                    className="hover:bg-muted -mx-2 flex items-baseline justify-between gap-3 rounded-md px-2 py-2.5 transition-colors"
                  >
                    <div className="min-w-0">
                      <div className="text-foreground truncate text-sm leading-tight font-medium">
                        {row.property_name ?? `#${row.property}`}
                      </div>
                      <div className="text-muted-foreground truncate text-xs">
                        {row.guest_name ?? row.reference}
                      </div>
                    </div>
                    <div className="text-muted-foreground shrink-0 font-mono text-[11px] tracking-wider">
                      {row.reference}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </article>
  );
}

function SkeletonRows() {
  return (
    <ul className="divide-border divide-y">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="py-2.5">
          <div className="bg-muted h-4 w-48 animate-pulse rounded" />
          <div className="bg-muted mt-1.5 h-3 w-28 animate-pulse rounded" />
        </li>
      ))}
    </ul>
  );
}
