import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format/date";
import type { TFunction } from "i18next";
import type { UserSummary } from "@/features/users/schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

function fullName(row: UserSummary): string {
  const name = `${row.first_name ?? ""} ${row.last_name ?? ""}`.trim();
  return name || "—";
}

export function userColumns(t: TFunction<"admin">): ColumnDef<UserSummary>[] {
  return [
    {
      accessorKey: "email",
      header: t("users.columns.email"),
      enableSorting: true,
      cell: ({ row }) => <span className="text-foreground font-medium">{row.original.email}</span>,
    },
    {
      id: "name",
      header: t("users.columns.name"),
      enableSorting: false,
      cell: ({ row }) => <span className="text-sm">{fullName(row.original)}</span>,
    },
    {
      accessorKey: "role",
      header: t("users.columns.role"),
      enableSorting: false,
      cell: ({ row }) => {
        const r = row.original.role;
        if (!r) return MUTED_DASH;
        const key = `users.roles.${r}`;
        const label = t(key as "users.roles.admin");
        return <Badge variant="outline">{label === key ? r : label}</Badge>;
      },
    },
    {
      accessorKey: "is_active",
      header: t("users.columns.is_active"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.is_active ? (
          <Badge variant="default">{t("users.is_active.yes")}</Badge>
        ) : (
          <Badge variant="secondary">{t("users.is_active.no")}</Badge>
        ),
    },
    {
      id: "last_login",
      header: t("users.columns.last_login"),
      enableSorting: true,
      cell: ({ row }) => {
        const value = row.original.last_login;
        return value ? <span className="text-sm">{formatDateTime(value)}</span> : MUTED_DASH;
      },
    },
    {
      id: "date_joined",
      header: t("users.columns.created_at"),
      enableSorting: true,
      cell: ({ row }) => {
        const value = row.original.date_joined;
        return value ? <span className="text-sm">{formatDateTime(value)}</span> : MUTED_DASH;
      },
    },
  ];
}
