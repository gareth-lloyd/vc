import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ColumnDef } from "@tanstack/react-table";
import { StagePips } from "@/components/data/StagePips";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { BookingListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

export function useBookingColumns(): ColumnDef<BookingListItem>[] {
  const { t } = useTranslation("bookings");
  return useMemo<ColumnDef<BookingListItem>[]>(
    () => [
      {
        accessorKey: "reference",
        header: t("columns.ref"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-foreground font-mono text-sm">{row.original.reference}</span>
        ),
      },
      {
        id: "property",
        header: t("columns.villa"),
        enableSorting: false,
        cell: ({ row }) => {
          const name = row.original.property_name;
          return name ? <span className="text-sm">{name}</span> : MUTED_DASH;
        },
      },
      {
        id: "guest",
        header: t("columns.guest"),
        enableSorting: false,
        cell: ({ row }) => {
          const { guest_name, guest_email } = row.original;
          if (!guest_name && !guest_email) return MUTED_DASH;
          return (
            <div className="text-sm">
              {guest_name ? <div>{guest_name}</div> : null}
              {guest_email ? (
                <div className="text-muted-foreground text-xs">{guest_email}</div>
              ) : null}
            </div>
          );
        },
      },
      {
        accessorKey: "date_from",
        header: t("columns.dates"),
        enableSorting: true,
        cell: ({ row }) => {
          const { date_from, date_to, night_count } = row.original;
          return (
            <div className="text-sm">
              <div>
                {formatDate(date_from)} – {formatDate(date_to)}
              </div>
              {night_count != null ? (
                <div className="text-muted-foreground text-xs">
                  {t("columns.nights", { count: night_count })}
                </div>
              ) : null}
            </div>
          );
        },
      },
      {
        accessorKey: "status",
        header: t("columns.stage"),
        enableSorting: true,
        cell: ({ row }) => (
          <div className="space-y-1">
            <StagePips status={row.original.status} />
            <StatusBadge status={row.original.status} />
          </div>
        ),
      },
      {
        id: "total",
        header: t("columns.total"),
        enableSorting: false,
        cell: ({ row }) => {
          const { total, rental_price, currency_code } = row.original;
          const amount = total ?? rental_price;
          return <span className="text-sm">{formatMoney(amount, currency_code ?? null)}</span>;
        },
      },
    ],
    [t],
  );
}
