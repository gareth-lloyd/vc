import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import type { TFunction } from "i18next";
import type { Country } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

export function countryColumns(t: TFunction<"admin">): ColumnDef<Country>[] {
  return [
    {
      accessorKey: "iso2",
      header: t("countries.columns.iso2"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-foreground font-mono text-sm">{row.original.iso2}</span>
      ),
    },
    {
      accessorKey: "name",
      header: t("countries.columns.name"),
      enableSorting: false,
      cell: ({ row }) => <span className="font-medium">{row.original.name}</span>,
    },
    {
      accessorKey: "iso3",
      header: t("countries.columns.iso3"),
      enableSorting: false,
      cell: ({ row }) => row.original.iso3 || MUTED_DASH,
    },
    {
      accessorKey: "dial_code",
      header: t("countries.columns.dial_code"),
      enableSorting: false,
      cell: ({ row }) => row.original.dial_code || MUTED_DASH,
    },
    {
      accessorKey: "sort_order",
      header: t("countries.columns.sort_order"),
      enableSorting: false,
    },
    {
      accessorKey: "is_active",
      header: t("countries.columns.is_active"),
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
