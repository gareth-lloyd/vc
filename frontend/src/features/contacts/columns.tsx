import type { ColumnDef } from "@tanstack/react-table";
import { StatusBadge } from "@/components/data/StatusBadge";
import { contactDisplayName } from "./display";
import type { ContactListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

function primaryEmail(row: ContactListItem): string | null {
  if (row.primary_email) return row.primary_email;
  if (!row.emails?.length) return null;
  return (row.emails.find((e) => e.is_primary) ?? row.emails[0]).email;
}

function primaryPhone(row: ContactListItem): string | null {
  if (row.primary_phone) return row.primary_phone;
  if (!row.phones?.length) return null;
  return (row.phones.find((p) => p.is_primary) ?? row.phones[0]).number;
}

export const contactColumns: ColumnDef<ContactListItem>[] = [
  {
    id: "name",
    header: "Name",
    enableSorting: false,
    cell: ({ row }) => {
      const c = row.original;
      const label = contactDisplayName({
        id: c.id,
        first_name: c.first_name,
        last_name: c.last_name,
        company: c.company,
        emails: [],
        phones: [],
      });
      const titled = c.title && (c.first_name || c.last_name) ? `${c.title} ${label}` : label;
      return <span className="text-foreground font-medium">{titled}</span>;
    },
  },
  {
    accessorKey: "company",
    header: "Company",
    enableSorting: false,
    cell: ({ row }) => {
      const company = row.original.company;
      // Avoid duplicating the company name when it's already serving as the display name.
      const hasPerson = !!(row.original.first_name || row.original.last_name);
      if (!company || !hasPerson) return MUTED_DASH;
      return <span className="text-sm">{company}</span>;
    },
  },
  {
    id: "primary_email",
    header: "Email",
    enableSorting: false,
    cell: ({ row }) => {
      const value = primaryEmail(row.original);
      return value ? <span className="text-sm">{value}</span> : MUTED_DASH;
    },
  },
  {
    id: "primary_phone",
    header: "Phone",
    enableSorting: false,
    cell: ({ row }) => {
      const value = primaryPhone(row.original);
      return value ? <span className="text-sm">{value}</span> : MUTED_DASH;
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    enableSorting: false,
    cell: ({ getValue }) => {
      const value = getValue<string | null | undefined>();
      return value ? <StatusBadge status={value} /> : MUTED_DASH;
    },
  },
];
