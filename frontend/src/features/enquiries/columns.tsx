import type { ColumnDef } from "@tanstack/react-table";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import { ENQUIRY_STATUS_LABELS, type EnquiryListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

function guestName(row: EnquiryListItem): string {
  const name = `${row.first_name ?? ""} ${row.last_name ?? ""}`.trim();
  return name || row.email || "—";
}

export const enquiryColumns: ColumnDef<EnquiryListItem>[] = [
  {
    accessorKey: "reference",
    header: "Ref",
    enableSorting: false,
    cell: ({ row }) => (
      <span className="text-foreground font-mono text-sm">{row.original.reference}</span>
    ),
  },
  {
    id: "guest",
    header: "Guest",
    enableSorting: false,
    cell: ({ row }) => {
      const name = guestName(row.original);
      return (
        <div className="text-sm">
          <div>{name}</div>
          {row.original.email ? (
            <div className="text-muted-foreground text-xs">{row.original.email}</div>
          ) : null}
        </div>
      );
    },
  },
  {
    accessorKey: "date_from",
    header: "Dates",
    enableSorting: true,
    cell: ({ row }) => {
      const { date_from, date_to } = row.original;
      if (!date_from && !date_to) return MUTED_DASH;
      return (
        <span className="text-sm">
          {formatDate(date_from ?? null)} – {formatDate(date_to ?? null)}
        </span>
      );
    },
  },
  {
    id: "party",
    header: "Party",
    enableSorting: false,
    cell: ({ row }) => {
      const { adults, children } = row.original;
      return (
        <span className="text-sm">
          {adults}A{children ? ` · ${children}C` : ""}
        </span>
      );
    },
  },
  {
    accessorKey: "site_source",
    header: "Source",
    enableSorting: false,
    cell: ({ row }) => (
      <span className="text-sm capitalize">{row.original.site_source.replace(/_/g, " ")}</span>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    enableSorting: true,
    cell: ({ row }) => <StatusBadge status={ENQUIRY_STATUS_LABELS[row.original.status]} />,
  },
  {
    accessorKey: "created_at",
    header: "Created",
    enableSorting: true,
    cell: ({ row }) => (
      <span className="text-sm">{formatDate(row.original.created_at ?? null)}</span>
    ),
  },
];
