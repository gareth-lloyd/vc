import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { ChevronLeft, Plus } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { formatNightRange } from "@/lib/format/date";
import { nightRangeParts } from "@/lib/nights";
import { BlockRequestDialog } from "./BlockRequestDialog";
import {
  useCancelBlockRequest,
  useOwnerBlockRequests,
  useOwnerProperty,
  useOwnerPropertyCalendar,
} from "./hooks";
import type { OwnerBlockRequest, OwnerCalendarCell } from "./schemas";

// A live (approved) block can be lifted to release the hold. Cancelled rows
// are terminal.
const CANCELLABLE_STATUSES: ReadonlySet<OwnerBlockRequest["status"]> = new Set(["approved"]);

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
const CELL_BASE = "flex h-10 w-full items-center justify-center rounded text-sm";

type CellKind = "available" | "booked" | "hold";

// Owner calendar reasons collapse to three buckets: a booked stay, a VC hold
// (any other unavailable reason), or available. No guest identity is exposed.
function cellKind(cell: OwnerCalendarCell | undefined): CellKind {
  if (!cell || cell.available) return "available";
  if (cell.reason === "booked") return "booked";
  return "hold";
}

function kindClasses(kind: CellKind): string {
  switch (kind) {
    case "booked":
      return "bg-primary text-primary-foreground font-medium";
    case "hold":
      return "bg-hold/35 text-hold";
    default:
      return "text-foreground";
  }
}

const LEGEND: CellKind[] = ["booked", "hold", "available"];

function legendSwatchClass(kind: CellKind): string {
  return kind === "available" ? "border-border border" : kindClasses(kind);
}

export function OwnerPropertyCalendarPage() {
  const { t } = useTranslation("owner");
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const propertyId = id ? Number(id) : undefined;
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(new Date()));
  const [blockDialogOpen, setBlockDialogOpen] = useState(false);

  const property = useOwnerProperty(propertyId);

  const { windowStart, windowEnd, days } = useMemo(() => {
    const ws = startOfWeek(startOfMonth(viewMonth), { weekStartsOn: 1 });
    const we = endOfWeek(endOfMonth(viewMonth), { weekStartsOn: 1 });
    return { windowStart: ws, windowEnd: we, days: eachDayOfInterval({ start: ws, end: we }) };
  }, [viewMonth]);

  const from = format(windowStart, "yyyy-MM-dd");
  const to = format(windowEnd, "yyyy-MM-dd");
  const calendar = useOwnerPropertyCalendar(propertyId, from, to);

  const cellByIso = useMemo(() => {
    const map = new Map<string, OwnerCalendarCell>();
    for (const cell of calendar.data?.cells ?? []) map.set(cell.date, cell);
    return map;
  }, [calendar.data]);

  const title = property.data?.display_name || property.data?.name || t("calendar.title");

  const canRequestBlock = calendar.data?.can_request_block ?? false;
  const blockRequests = useOwnerBlockRequests(propertyId != null ? { property: propertyId } : {});
  const cancelMutation = useCancelBlockRequest();

  const handleCancel = async (request: OwnerBlockRequest) => {
    try {
      await cancelMutation.mutateAsync(request.id);
      toast.success(t("blocks.toasts.cancelled"));
    } catch (error) {
      if (!(error instanceof ApiError && error.isClientError())) {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  return (
    <div>
      {propertyId != null && blockDialogOpen ? (
        <BlockRequestDialog
          propertyId={propertyId}
          open={blockDialogOpen}
          onOpenChange={setBlockDialogOpen}
        />
      ) : null}
      <PageHeader
        title={title}
        breadcrumbs={[{ label: t("nav.properties"), to: "/owner/properties" }, { label: title }]}
        actions={
          <div className="flex items-center gap-2">
            {canRequestBlock ? (
              <Button size="sm" onClick={() => setBlockDialogOpen(true)}>
                <Plus className="mr-1 size-4" /> {t("blocks.request_button")}
              </Button>
            ) : null}
            <Button variant="outline" size="sm" onClick={() => navigate("/owner/properties")}>
              <ChevronLeft className="mr-1 size-4" /> {t("calendar.back")}
            </Button>
          </div>
        }
      />
      <div className="space-y-6 px-6 pb-12">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setViewMonth((m) => subMonths(m, 1))}
            aria-label={t("calendar.prev_month")}
          >
            &#x25C0;
          </Button>
          <h2 className="text-foreground min-w-[140px] text-center text-base font-semibold">
            {format(viewMonth, "MMMM yyyy")}
          </h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setViewMonth((m) => addMonths(m, 1))}
            aria-label={t("calendar.next_month")}
          >
            &#x25B6;
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setViewMonth(startOfMonth(new Date()))}>
            {t("calendar.today")}
          </Button>
        </div>

        <div className="flex flex-wrap gap-4 text-xs">
          {LEGEND.map((kind) => (
            <span key={kind} className="flex items-center gap-1">
              <span className={`inline-block h-3 w-3 rounded ${legendSwatchClass(kind)}`} />{" "}
              {t(`calendar.legend.${kind}`)}
            </span>
          ))}
        </div>

        {calendar.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : calendar.isError ? (
          <ErrorState description={t("calendar.load_failed")} onRetry={() => calendar.refetch()} />
        ) : (
          <div className="grid grid-cols-7 gap-1">
            {WEEKDAYS.map((d) => (
              <div
                key={d}
                className="text-muted-foreground flex h-8 items-center justify-center text-xs font-medium"
              >
                {d}
              </div>
            ))}
            {days.map((day) => {
              const iso = format(day, "yyyy-MM-dd");
              const inMonth = isSameMonth(day, viewMonth);
              const dayNum = format(day, "d");
              if (!inMonth) {
                return (
                  <div key={iso} className={`${CELL_BASE} text-muted-foreground/40`}>
                    {dayNum}
                  </div>
                );
              }
              const cell = cellByIso.get(iso);
              const kind = cellKind(cell);
              const dateLabel = format(day, "d MMMM");
              return (
                <div
                  key={iso}
                  className={`${CELL_BASE} ${kindClasses(kind)}`}
                  aria-label={t("calendar.cell_aria", {
                    date: dateLabel,
                    status: t(`calendar.legend.${kind}`),
                  })}
                >
                  {dayNum}
                </div>
              );
            })}
          </div>
        )}

        <section className="space-y-3">
          <h2 className="text-foreground text-base font-semibold">{t("blocks.list_title")}</h2>
          {blockRequests.isError ? (
            <ErrorState
              description={t("blocks.load_failed")}
              onRetry={() => blockRequests.refetch()}
            />
          ) : (blockRequests.data?.length ?? 0) === 0 ? (
            <p className="text-muted-foreground text-sm">{t("blocks.empty")}</p>
          ) : (
            <ul className="divide-border bg-card shadow-card divide-y rounded-lg border">
              {blockRequests.data?.map((request) => (
                <li key={request.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="space-y-0.5">
                    <div className="text-sm font-medium">
                      {(() => {
                        const parts = nightRangeParts(request.date_from, request.date_to);
                        return t("calendar.night_range", {
                          range: formatNightRange(parts.firstNight, parts.lastNight),
                          count: parts.nights,
                        });
                      })()}
                    </div>
                    <div className="text-muted-foreground text-xs">
                      {t(`blocks.kind.${request.kind}`)}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="secondary">{t(`blocks.status.${request.status}`)}</Badge>
                    {CANCELLABLE_STATUSES.has(request.status) ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCancel(request)}
                        disabled={cancelMutation.isPending}
                      >
                        {t("blocks.actions.cancel_request")}
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
