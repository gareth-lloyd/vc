import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ColumnDef } from "@tanstack/react-table";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/money";
import type { OwnerBookingListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

// Money columns are rendered only when the API includes the field — the server
// omits rental_price entirely for properties without a view_full_money grant.
export function useOwnerBookingColumns(showMoney: boolean): ColumnDef<OwnerBookingListItem>[] {
  const { t } = useTranslation("owner");
  return useMemo<ColumnDef<OwnerBookingListItem>[]>(() => {
    const cols: ColumnDef<OwnerBookingListItem>[] = [
      {
        accessorKey: "reference",
        header: t("bookings.columns.reference"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-foreground font-mono text-sm">{row.original.reference}</span>
        ),
      },
      {
        id: "property",
        header: t("bookings.columns.property"),
        enableSorting: false,
        cell: ({ row }) => {
          const name = row.original.property_name;
          return name ? <span className="text-sm">{name}</span> : MUTED_DASH;
        },
      },
      {
        id: "guest",
        header: t("bookings.columns.guest"),
        enableSorting: false,
        cell: ({ row }) => {
          const name = row.original.guest_name;
          return name ? <span className="text-sm">{name}</span> : MUTED_DASH;
        },
      },
      {
        accessorKey: "date_from",
        header: t("bookings.columns.stay"),
        enableSorting: true,
        cell: ({ row }) => (
          <span className="text-sm">
            {formatDate(row.original.date_from)} – {formatDate(row.original.date_to)}
          </span>
        ),
      },
      {
        id: "party",
        header: t("bookings.columns.party"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-sm tabular-nums">
            {t("bookings.party", {
              adults: row.original.adults,
              children: row.original.children,
            })}
          </span>
        ),
      },
    ];

    if (showMoney) {
      cols.push({
        id: "rental_price",
        header: t("bookings.columns.rental_price"),
        enableSorting: false,
        cell: ({ row }) => {
          const { rental_price, currency_code } = row.original;
          if (rental_price == null) return MUTED_DASH;
          return (
            <span className="text-sm tabular-nums">{formatMoney(rental_price, currency_code)}</span>
          );
        },
      });
    }

    cols.push({
      accessorKey: "status",
      header: t("bookings.columns.status"),
      enableSorting: true,
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    });

    return cols;
  }, [t, showMoney]);
}
