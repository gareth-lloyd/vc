import type { ColumnDef } from "@tanstack/react-table";
import type { TFunction } from "i18next";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDateTime } from "@/lib/format/date";
import type { EmailTemplateListItem } from "./schemas";

export function emailTemplateColumns(t: TFunction<"admin">): ColumnDef<EmailTemplateListItem>[] {
  return [
    {
      accessorKey: "title",
      header: t("email_templates.columns.title"),
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="text-foreground font-medium">{row.original.title}</span>
          <span className="text-muted-foreground font-mono text-xs">{row.original.key}</span>
        </div>
      ),
    },
    {
      accessorKey: "version",
      header: t("email_templates.columns.version"),
      enableSorting: false,
      cell: ({ row }) => <span className="tabular-nums">v{row.original.version}</span>,
    },
    {
      accessorKey: "is_active",
      header: t("email_templates.columns.is_active"),
      enableSorting: false,
      cell: ({ row }) => <StatusBadge status={row.original.is_active ? "active" : "archived"} />,
    },
    {
      accessorKey: "updated_at",
      header: t("email_templates.columns.updated_at"),
      enableSorting: false,
      cell: ({ row }) => <span className="text-sm">{formatDateTime(row.original.updated_at)}</span>,
    },
  ];
}
