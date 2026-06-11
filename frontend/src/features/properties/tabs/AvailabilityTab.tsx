import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useOutletContext } from "react-router-dom";
import { format, parseISO } from "date-fns";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { cellsByDate, useMonthGrid, WEEKDAYS } from "@/lib/monthGrid";
import { reasonClasses } from "../availabilityTokens";
import {
  usePropertyAvailabilityCalendar,
  usePropertyBookingsForRange,
  usePropertyHolds,
  useDeletePropertyBlock,
} from "../hooks";
import type { AvailabilityCell, PropertyDetail } from "../schemas";
import {
  AvailabilityBlockFormDialog,
  type EditableBlock,
} from "../components/AvailabilityBlockFormDialog";

interface AvailabilityContext {
  property: PropertyDetail;
}

// Reasons that carry an operator-editable block (the server only sets
// block_id for these).
const EDITABLE_REASONS = new Set(["owner_block", "maintenance", "manual"]);

const LEGEND_REASONS = [
  "available",
  "booked",
  "quotation",
  "owner_block",
  "maintenance",
  "manual",
  "changeover",
] as const;

function legendSwatchClass(reason: string): string {
  if (reason === "available") return "border-border border";
  if (reason === "changeover") return "from-primary bg-gradient-to-b to-info/40";
  return reasonClasses(reason);
}

const CELL_BASE = "flex h-10 w-full items-center justify-center rounded text-sm transition-colors";

export function AvailabilityTab() {
  const { t } = useTranslation("properties");
  const { property } = useOutletContext<AvailabilityContext>();
  const canWrite = useHasReservationsRole();
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<EditableBlock | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const { viewMonth, days, from, to, isCurrentMonth, goToPreviousMonth, goToNextMonth, goToToday } =
    useMonthGrid();

  const calendar = usePropertyAvailabilityCalendar(property.id, from, to);
  const bookings = usePropertyBookingsForRange(property.id, from, to);
  // Holds only resolve the full date range / notes for the edit dialog —
  // the calendar cells deliberately don't carry them. Read-only users never
  // open the edit dialog, so skip the fetch entirely for them.
  const holds = usePropertyHolds(canWrite ? property.id : undefined, from, to);
  const deleteMutation = useDeletePropertyBlock(property.id);

  const cellByIso = useMemo(
    () => cellsByDate<AvailabilityCell>(calendar.data?.cells),
    [calendar.data],
  );

  const bookingIdByIso = useMemo(() => {
    const map = new Map<string, number>();
    for (const b of bookings.data?.results ?? []) {
      const fromD = parseISO(b.date_from);
      const toD = parseISO(b.date_to);
      for (const day of days) {
        if (day >= fromD && day < toD) map.set(format(day, "yyyy-MM-dd"), b.id);
      }
    }
    return map;
  }, [bookings.data, days]);

  const holdById = useMemo(() => {
    const map = new Map<number, EditableBlock>();
    for (const h of holds.data ?? []) {
      if (EDITABLE_REASONS.has(h.reason)) {
        map.set(h.id, {
          id: h.id,
          reason: h.reason as EditableBlock["reason"],
          date_from: h.date_from,
          date_to: h.date_to,
          notes: h.notes ?? "",
        });
      }
    }
    return map;
  }, [holds.data]);

  const reasonLabel = (reason: string) =>
    reason ? t(`availability.reason_labels.${reason}`) : t("availability.reason_labels.available");

  const handleDelete = async () => {
    if (deleting == null) return;
    try {
      await deleteMutation.mutateAsync({ blockId: deleting });
      toast.success(t("availability.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("availability.toasts.delete_failed"));
    }
  };

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setAddOpen(true)}>
      {t("availability.add_block")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("availability.add_block")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("availability.add_block_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={goToPreviousMonth}
            aria-label={t("availability.prev_month")}
          >
            &#x25C0;
          </Button>
          <h2 className="text-foreground min-w-[140px] text-center text-base font-semibold">
            {format(viewMonth, "MMMM yyyy")}
          </h2>
          <Button
            variant="outline"
            size="sm"
            onClick={goToNextMonth}
            aria-label={t("availability.next_month")}
          >
            &#x25B6;
          </Button>
          <Button variant="ghost" size="sm" onClick={goToToday}>
            {t("availability.today")}
          </Button>
        </div>
        {addButton}
      </div>

      <div className="flex flex-wrap gap-4 text-xs">
        {LEGEND_REASONS.map((r) => (
          <span key={r} className="flex items-center gap-1">
            <span className={`inline-block h-3 w-3 rounded ${legendSwatchClass(r)}`} />{" "}
            {t(`availability.legend.${r}`)}
          </span>
        ))}
      </div>

      {calendar.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : calendar.isError ? (
        <ErrorState
          title={t("availability.load_failed_title")}
          description={t("availability.load_failed_body")}
          onRetry={() => calendar.refetch()}
        />
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
            const dayNum = format(day, "d");
            // Adjacent-month days render with real availability state (the
            // query window is week-aligned), just dimmed.
            const base = isCurrentMonth(day) ? CELL_BASE : `${CELL_BASE} opacity-40`;

            const cell = cellByIso.get(iso);
            const reason = cell && !cell.available ? cell.reason : "";
            const dateLabel = format(day, "d MMMM");

            if (cell?.segments) {
              const { am, pm } = cell.segments;
              return (
                <div
                  key={iso}
                  className={`${base} relative overflow-hidden p-0`}
                  aria-label={t("availability.cell_aria_split", {
                    date: dateLabel,
                    am: reasonLabel(am.reason),
                    pm: reasonLabel(pm.reason),
                  })}
                >
                  <span className={`absolute inset-x-0 top-0 h-1/2 ${reasonClasses(am.reason)}`} />
                  <span
                    className={`absolute inset-x-0 bottom-0 h-1/2 ${reasonClasses(pm.reason)}`}
                  />
                  <span className="relative z-10 font-medium">{dayNum}</span>
                </div>
              );
            }

            if (reason === "booked") {
              const bookingId = bookingIdByIso.get(iso);
              if (bookingId != null) {
                return (
                  <Link
                    key={iso}
                    to={`/bookings/${bookingId}`}
                    className={`${base} ${reasonClasses("booked")}`}
                    title={t("availability.booked_title")}
                  >
                    {dayNum}
                  </Link>
                );
              }
              return (
                <div
                  key={iso}
                  className={`${base} ${reasonClasses("booked")}`}
                  aria-label={t("availability.cell_aria", {
                    date: dateLabel,
                    status: reasonLabel("booked"),
                  })}
                >
                  {dayNum}
                </div>
              );
            }

            // A quotation hold links through to its owning quotation — read
            // only; editing stays with the quotation itself.
            if (reason === "quotation" && cell?.quotation_id != null) {
              return (
                <Link
                  key={iso}
                  to={`/enquiries/quotes/${cell.quotation_id}`}
                  className={`${base} ${reasonClasses("quotation")}`}
                  title={t("availability.quotation_title")}
                  aria-label={t("availability.cell_aria", {
                    date: dateLabel,
                    status: reasonLabel("quotation"),
                  })}
                >
                  {dayNum}
                </Link>
              );
            }

            if (reason === "") {
              return (
                <div key={iso} className={`${base} text-foreground`}>
                  {dayNum}
                </div>
              );
            }

            const blockId = cell?.block_id ?? null;
            const block =
              canWrite && blockId != null && EDITABLE_REASONS.has(reason)
                ? holdById.get(blockId)
                : undefined;
            const cellClassName = `${base} ${reasonClasses(reason)}${
              block ? " cursor-pointer" : ""
            }`;
            const cellAria = t("availability.cell_aria", {
              date: dateLabel,
              status: reasonLabel(reason),
            });

            if (!block) {
              return (
                <div key={iso} className={cellClassName} aria-label={cellAria}>
                  {dayNum}
                </div>
              );
            }

            return (
              <DropdownMenu key={iso}>
                <DropdownMenuTrigger asChild>
                  <button type="button" className="w-full" aria-label={cellAria}>
                    <div className={cellClassName}>{dayNum}</div>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => setEditing(block)}>
                    {t("availability.block_dialog.edit_title")}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="text-destructive"
                    onClick={() => setDeleting(block.id)}
                  >
                    {t("availability.delete_confirm.confirm")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            );
          })}
        </div>
      )}

      {addOpen ? (
        <AvailabilityBlockFormDialog
          propertyId={property.id}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <AvailabilityBlockFormDialog
          propertyId={property.id}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          block={editing}
        />
      ) : null}
      {deleting != null ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("availability.delete_confirm.title")}
          description={t("availability.delete_confirm.description")}
          confirmLabel={t("availability.delete_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
