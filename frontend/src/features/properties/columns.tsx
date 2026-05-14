import type { ColumnDef } from "@tanstack/react-table";
import i18n from "@/i18n";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import type { PropertyListItem } from "./schemas";

export const propertyColumns: ColumnDef<PropertyListItem>[] = [
  {
    accessorKey: "name",
    header: () => i18n.t("properties:columns.name"),
    enableSorting: true,
    cell: ({ row }) => {
      const { name, display_name } = row.original;
      return (
        <div>
          <div className="text-foreground font-medium">{name}</div>
          {display_name && display_name !== name ? (
            <div className="text-muted-foreground text-xs">{display_name}</div>
          ) : null}
        </div>
      );
    },
  },
  {
    accessorKey: "licence_number",
    header: () => i18n.t("properties:columns.licence"),
    enableSorting: false,
    cell: ({ getValue }) => {
      const value = getValue<string | null>();
      return value ? (
        <span className="text-sm">{value}</span>
      ) : (
        <span className="text-muted-foreground">—</span>
      );
    },
  },
  {
    accessorKey: "status",
    header: () => i18n.t("properties:columns.status"),
    enableSorting: false,
    cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
  },
  {
    accessorKey: "channel",
    header: () => i18n.t("properties:columns.channel"),
    enableSorting: false,
    cell: ({ getValue }) => {
      const value = getValue<string | null>();
      return value ? (
        <span className="text-sm capitalize">{value}</span>
      ) : (
        <span className="text-muted-foreground">—</span>
      );
    },
  },
  {
    accessorKey: "updated_at",
    header: () => i18n.t("properties:columns.updated"),
    enableSorting: true,
    cell: ({ getValue }) => (
      <span className="text-sm">{formatDate(getValue<string | null>())}</span>
    ),
  },
];
