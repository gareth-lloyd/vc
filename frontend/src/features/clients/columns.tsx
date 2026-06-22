import type { ColumnDef } from "@tanstack/react-table";
import i18n from "@/i18n";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/data/StatusBadge";
import { clientDisplayName } from "./display";
import type { ClientListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

export const clientColumns: ColumnDef<ClientListItem>[] = [
  {
    id: "name",
    header: () => i18n.t("clients:fields.name"),
    enableSorting: false,
    cell: ({ row }) => (
      <span className="text-foreground font-medium">{clientDisplayName(row.original)}</span>
    ),
  },
  {
    accessorKey: "primary_email",
    header: () => i18n.t("clients:fields.email"),
    enableSorting: false,
    cell: ({ row }) => {
      const email = row.original.primary_email;
      return email ? <span className="text-sm">{email}</span> : MUTED_DASH;
    },
  },
  {
    accessorKey: "primary_phone",
    header: () => i18n.t("clients:fields.phone"),
    enableSorting: false,
    cell: ({ row }) => {
      const phone = row.original.primary_phone;
      return phone ? <span className="text-sm">{phone}</span> : MUTED_DASH;
    },
  },
  {
    id: "capacity",
    header: () => i18n.t("clients:fields.capacity"),
    enableSorting: false,
    cell: ({ row }) =>
      row.original.is_agent ? (
        <Badge variant="secondary">{i18n.t("clients:capacity.agent")}</Badge>
      ) : (
        <Badge variant="outline">{i18n.t("clients:capacity.direct")}</Badge>
      ),
  },
  {
    accessorKey: "status",
    header: () => i18n.t("clients:fields.status"),
    enableSorting: false,
    cell: ({ getValue }) => {
      const value = getValue<string | null | undefined>();
      return value ? <StatusBadge status={value} /> : MUTED_DASH;
    },
  },
];
