import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ColumnDef } from "@tanstack/react-table";
import { formatDate } from "@/lib/format/date";
import type { OwnerUpcomingArrival } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

export function useOwnerArrivalColumns(): ColumnDef<OwnerUpcomingArrival>[] {
  const { t } = useTranslation("owner");
  return useMemo<ColumnDef<OwnerUpcomingArrival>[]>(
    () => [
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
        accessorKey: "date_from",
        header: t("bookings.columns.stay"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-sm">
            {formatDate(row.original.date_from)} – {formatDate(row.original.date_to)}
          </span>
        ),
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
    ],
    [t],
  );
}
