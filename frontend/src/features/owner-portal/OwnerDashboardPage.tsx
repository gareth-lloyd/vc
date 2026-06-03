import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/layout/PageHeader";
import { Section } from "@/components/data/Section";
import { DataTable } from "@/components/data/DataTable";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import { cn } from "@/lib/cn";
import { useOwnerDashboard } from "./hooks";
import { useOwnerArrivalColumns } from "./arrivalColumns";

function KpiCard({
  label,
  value,
  hue = "brand",
}: {
  label: string;
  value: ReactNode;
  hue?: "brand" | "accent" | "info";
}) {
  return (
    <div className="bg-card shadow-card relative overflow-hidden rounded-lg border px-5 py-4">
      <span
        aria-hidden
        className={cn(
          "absolute top-3 bottom-3 left-0 w-[3px] rounded-r",
          hue === "brand" && "bg-brand-500",
          hue === "accent" && "bg-accent-500",
          hue === "info" && "bg-info",
        )}
      />
      <div className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
        {label}
      </div>
      <div className="text-foreground mt-1 font-serif text-3xl font-semibold tracking-tight tabular-nums">
        {value}
      </div>
    </div>
  );
}

export function OwnerDashboardPage() {
  const { t } = useTranslation("owner");
  const query = useOwnerDashboard();
  const arrivalColumns = useOwnerArrivalColumns();

  if (query.isError) {
    return (
      <div>
        <PageHeader title={t("dashboard.title")} />
        <div className="p-6">
          <ErrorState description={t("dashboard.load_failed")} onRetry={() => query.refetch()} />
        </div>
      </div>
    );
  }

  const data = query.data;
  const notShared = t("dashboard.not_shared");

  // by_status is an arbitrary status->count map. Render each present status as a
  // small chip rather than enumerating the full enum.
  const statusEntries = data ? Object.entries(data.properties.by_status) : [];

  return (
    <div>
      <PageHeader title={t("dashboard.title")} subtitle={t("dashboard.subtitle")} />
      <div className="space-y-8 px-6 pb-12">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {query.isLoading || !data ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))
          ) : (
            <>
              <KpiCard label={t("dashboard.kpis.ytd_bookings")} value={data.ytd.bookings} />
              <KpiCard
                label={t("dashboard.kpis.ytd_gross")}
                hue="accent"
                value={
                  data.ytd.gross_revenue != null
                    ? formatMoney(data.ytd.gross_revenue, "EUR")
                    : notShared
                }
              />
              <KpiCard
                label={t("dashboard.kpis.your_share")}
                hue="accent"
                value={
                  data.ytd.net_to_owner != null
                    ? formatMoney(data.ytd.net_to_owner, "EUR")
                    : notShared
                }
              />
              <KpiCard
                label={t("dashboard.kpis.properties")}
                hue="info"
                value={data.properties.total}
              />
            </>
          )}
        </div>

        {statusEntries.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {statusEntries.map(([status, count]) => (
              <span
                key={status}
                className="border-border bg-muted/40 text-muted-foreground inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs"
              >
                <span className="capitalize">{status}</span>
                <span className="text-foreground font-medium tabular-nums">{count}</span>
              </span>
            ))}
          </div>
        ) : null}

        <Section title={t("dashboard.upcoming_arrivals")}>
          <DataTable
            columns={arrivalColumns}
            data={data?.upcoming_arrivals}
            isLoading={query.isLoading}
            pageIndex={0}
            pageCount={1}
            sorting={[]}
            onSortingChange={() => {}}
            onPageChange={() => {}}
            rowKey={(row) => `${row.reference}-${formatDate(row.date_from)}`}
            emptyContent={<EmptyState title={t("dashboard.no_arrivals")} />}
          />
        </Section>
      </div>
    </div>
  );
}
