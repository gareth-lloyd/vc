import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import type { TFunction } from "i18next";
import type { Currency } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

export function currencyColumns(t: TFunction<"admin">): ColumnDef<Currency>[] {
  return [
    {
      accessorKey: "code",
      header: t("currencies.columns.code"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-foreground font-mono text-sm">{row.original.code}</span>
      ),
    },
    {
      accessorKey: "name",
      header: t("currencies.columns.name"),
      enableSorting: false,
      cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
    },
    {
      accessorKey: "symbol",
      header: t("currencies.columns.symbol"),
      enableSorting: false,
      cell: ({ row }) => row.original.symbol || MUTED_DASH,
    },
    {
      accessorKey: "decimal_places",
      header: t("currencies.columns.decimal_places"),
      enableSorting: false,
    },
    {
      accessorKey: "is_active",
      header: t("currencies.columns.is_active"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.is_active ? (
          <Badge variant="default">{t("users.is_active.yes")}</Badge>
        ) : (
          <Badge variant="secondary">{t("users.is_active.no")}</Badge>
        ),
    },
  ];
}
