import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { TierBadge } from "@/components/data/TierBadge";
import { ApiError } from "@/lib/api/errors";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { formatDate } from "@/lib/format/date";
import { SERVICE_KEYS, serviceColorVar, type ServiceKey } from "@/styles/tokens";
import type { ServiceStatus } from "@/components/data/ServiceDot";
import { useConciergeOverview, useSetServiceStatus } from "./hooks";
import { serviceLabel, type ConciergeOverviewRow } from "./schemas";
import { CountdownPill } from "./components/CountdownPill";
import { ServiceStatusCell } from "./components/ServiceStatusCell";
import { ServiceMatrixLegend } from "./components/ServiceMatrixLegend";

export function ConciergeOverviewPage() {
  const { t } = useTranslation("concierge");
  const canWrite = useHasReservationsRole();
  const overview = useConciergeOverview();
  const setStatus = useSetServiceStatus();

  const handleSelect = async (
    row: ConciergeOverviewRow,
    service: ServiceKey,
    status: ServiceStatus,
  ) => {
    try {
      await setStatus.mutateAsync({ bookingId: row.id, service, status });
      toast.success(t("toasts.updated"));
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : t("toasts.update_failed");
      toast.error(message);
    }
  };

  return (
    <div className="pb-10">
      <PageHeader title={t("page.title")} subtitle={t("page.subtitle")} />
      <div className="space-y-6 px-6">
        {overview.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : overview.isError ? (
          <ErrorState
            title={t("error.title")}
            description={t("error.body")}
            onRetry={() => overview.refetch()}
          />
        ) : !overview.data?.length ? (
          <EmptyState title={t("empty.title")} description={t("empty.body")} />
        ) : (
          <>
            <div className="border-border shadow-card overflow-x-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-44">{t("columns.booking")}</TableHead>
                    <TableHead className="min-w-44">{t("columns.villa")}</TableHead>
                    <TableHead className="min-w-28">{t("columns.arrival")}</TableHead>
                    {SERVICE_KEYS.map((service) => (
                      <TableHead key={service} className="px-2 text-center">
                        <span className="flex flex-col items-center gap-1">
                          <span
                            aria-hidden
                            className="size-2.5 rounded-full"
                            style={{ backgroundColor: serviceColorVar[service] }}
                          />
                          <span className="text-[11px] leading-tight font-normal">
                            {serviceLabel(service)}
                          </span>
                        </span>
                      </TableHead>
                    ))}
                    <TableHead className="min-w-28">{t("columns.progress")}</TableHead>
                    <TableHead className="min-w-24">{t("columns.tier")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {overview.data.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>
                        <div className="font-medium">{row.reference}</div>
                        <div className="text-muted-foreground text-xs">{row.guest_name ?? "—"}</div>
                      </TableCell>
                      <TableCell>
                        <div>{row.property_name ?? "—"}</div>
                        <div className="text-muted-foreground text-xs">{row.region ?? "—"}</div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <CountdownPill days={row.arrival_in_days} />
                          <div className="text-muted-foreground text-xs">
                            {formatDate(row.date_from)}
                          </div>
                        </div>
                      </TableCell>
                      {SERVICE_KEYS.map((service) => (
                        <TableCell key={service} className="text-center">
                          <ServiceStatusCell
                            service={service}
                            status={row.services[service] ?? "not_started"}
                            reference={row.reference}
                            canWrite={canWrite}
                            onSelect={(status) => handleSelect(row, service, status)}
                          />
                        </TableCell>
                      ))}
                      <TableCell>
                        <ProgressBar
                          value={row.progress}
                          label={t("progress_label", { percent: row.progress })}
                        />
                      </TableCell>
                      <TableCell>
                        {row.tier ? <TierBadge tier={row.tier} compact /> : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <ServiceMatrixLegend />
          </>
        )}
      </div>
    </div>
  );
}

function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="bg-muted h-1.5 w-16 overflow-hidden rounded-full" aria-hidden>
        <div className="bg-primary h-full rounded-full" style={{ width: `${value}%` }} />
      </div>
      <span className="text-muted-foreground text-xs tabular-nums">{label}</span>
    </div>
  );
}
