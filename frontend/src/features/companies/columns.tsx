import type { ColumnDef } from "@tanstack/react-table";
import i18n from "@/i18n";
import { StatusBadge } from "@/components/data/StatusBadge";
import { companyDisplayName } from "./display";
import type { CompanyListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

export const companyColumns: ColumnDef<CompanyListItem>[] = [
  {
    id: "name",
    header: () => i18n.t("companies:fields.name"),
    enableSorting: false,
    cell: ({ row }) => (
      <span className="text-foreground font-medium">{companyDisplayName(row.original)}</span>
    ),
  },
  {
    accessorKey: "town",
    header: () => i18n.t("companies:fields.town"),
    enableSorting: false,
    cell: ({ row }) => {
      const town = row.original.town;
      return town ? <span className="text-sm">{town}</span> : MUTED_DASH;
    },
  },
  {
    accessorKey: "email",
    header: () => i18n.t("companies:fields.email"),
    enableSorting: false,
    cell: ({ row }) => {
      const email = row.original.email;
      return email ? <span className="text-sm">{email}</span> : MUTED_DASH;
    },
  },
  {
    accessorKey: "status",
    header: () => i18n.t("companies:fields.status"),
    enableSorting: false,
    cell: ({ getValue }) => {
      const value = getValue<string | null | undefined>();
      return value ? <StatusBadge status={value} /> : MUTED_DASH;
    },
  },
];
