import type { ColumnDef } from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import type { QuotationListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

// Factory keeps column headers translatable: TanStack reads `header` once per
// render, so we re-build the def whenever the active locale changes.
export function buildQuotationColumns(t: TFunction<"quotations">): ColumnDef<QuotationListItem>[] {
  return [
    {
      accessorKey: "reference",
      header: () => t("detail.summary.reference"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-foreground font-medium">{row.original.reference}</span>
      ),
    },
    {
      accessorKey: "status",
      header: () => t("detail.summary.status"),
      enableSorting: false,
      cell: ({ getValue }) => {
        const value = getValue<string | null | undefined>();
        return value ? <StatusBadge status={value} /> : MUTED_DASH;
      },
    },
    {
      accessorKey: "guest",
      header: () => t("detail.summary.guest"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.guest != null ? (
          <span className="text-sm">#{row.original.guest}</span>
        ) : (
          MUTED_DASH
        ),
    },
    {
      accessorKey: "currency",
      header: () => t("detail.summary.currency"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.currency ? (
          <span className="text-sm">{row.original.currency}</span>
        ) : (
          MUTED_DASH
        ),
    },
    {
      accessorKey: "created_at",
      header: () => t("detail.summary.created_at"),
      enableSorting: true,
      cell: ({ row }) => (
        <span className="text-sm">{formatDate(row.original.created_at ?? null)}</span>
      ),
    },
  ];
}
