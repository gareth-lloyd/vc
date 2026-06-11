import type { ColumnDef } from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import { quotationStatusLabel, type QuotationListItem } from "./schemas";

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
      cell: ({ row }) => {
        const value = row.original.status;
        return value ? (
          <StatusBadge status={value} label={quotationStatusLabel(value)} />
        ) : (
          MUTED_DASH
        );
      },
    },
    {
      accessorKey: "guest",
      header: () => t("detail.summary.guest"),
      enableSorting: false,
      cell: ({ row }) => {
        const name =
          row.original.guest_name ?? (row.original.guest != null ? `#${row.original.guest}` : null);
        return name ? <span className="text-sm">{name}</span> : MUTED_DASH;
      },
    },
    {
      accessorKey: "enquiry",
      header: () => t("detail.summary.enquiry"),
      enableSorting: false,
      cell: ({ row }) => {
        const ref =
          row.original.enquiry_reference ??
          (row.original.enquiry != null ? `#${row.original.enquiry}` : null);
        return ref ? <span className="font-mono text-xs">{ref}</span> : MUTED_DASH;
      },
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
