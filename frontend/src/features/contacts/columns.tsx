import type { ColumnDef } from "@tanstack/react-table";
import i18n from "@/i18n";
import { StatusBadge } from "@/components/data/StatusBadge";
import { PROPERTY_CONTACT_ROLES } from "@/lib/domain/contactRoles";
import { ContactTypeBadges } from "./components/ContactTypeBadges";
import { contactDisplayName } from "./display";
import type { ContactListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

// The canonical property-role set (mirrors backend `ContactRole`). Used as an
// allowlist so the Suppliers role column shows only genuine property roles and
// fails CLOSED — the synthetic capacities `contact_types` also carries
// ("customer", and "agent" from an agency link) and any future server-only role
// are dropped rather than leaking in as a raw chip.
const PROPERTY_ROLE_SET: ReadonlySet<string> = new Set(PROPERTY_CONTACT_ROLES);

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

const nameColumn: ColumnDef<ContactListItem> = {
  id: "name",
  header: () => i18n.t("contacts:fields.name"),
  enableSorting: false,
  cell: ({ row }) => {
    const c = row.original;
    const label = contactDisplayName({
      id: c.id,
      first_name: c.first_name,
      last_name: c.last_name,
      agency_detail: c.agency_detail,
      emails: [],
      phones: [],
    });
    const titled = c.title && (c.first_name || c.last_name) ? `${c.title} ${label}` : label;
    return <span className="text-foreground font-medium">{titled}</span>;
  },
};

const kindColumn: ColumnDef<ContactListItem> = {
  id: "kind",
  header: () => i18n.t("contacts:fields.kind"),
  enableSorting: false,
  cell: ({ row }) => {
    // `kind` is a typed enum (customer | contact) — building the i18n key from
    // it is allowed; anything else (incl. null) falls back to a dash.
    const value = row.original.kind;
    if (value !== "customer" && value !== "contact") return MUTED_DASH;
    return <span className="text-sm">{i18n.t(`contacts:kind.${value}`)}</span>;
  },
};

// GAP-048: the supplier's property role(s), from the `contact_types` derivation.
// Filtered to the property-role allowlist (drops the synthetic "customer"/"agent"
// capacities) and rendered with the shared `ContactTypeBadges` so the chips match
// the contact detail. Empty → a dash.
const roleColumn: ColumnDef<ContactListItem> = {
  id: "role",
  header: () => i18n.t("contacts:fields.role"),
  enableSorting: false,
  cell: ({ row }) => {
    const roles = (row.original.contact_types ?? []).filter((type) => PROPERTY_ROLE_SET.has(type));
    return roles.length > 0 ? <ContactTypeBadges types={roles} /> : MUTED_DASH;
  },
};

const agencyColumn: ColumnDef<ContactListItem> = {
  id: "agency",
  header: () => i18n.t("contacts:fields.agency"),
  enableSorting: false,
  cell: ({ row }) => {
    const agencyName = row.original.agency_detail?.name;
    // Avoid duplicating the agency name when it's already serving as the display name.
    const hasPerson = !!(row.original.first_name || row.original.last_name);
    if (!agencyName || !hasPerson) return MUTED_DASH;
    return <span className="text-sm">{agencyName}</span>;
  },
};

const emailColumn: ColumnDef<ContactListItem> = {
  id: "primary_email",
  header: () => i18n.t("contacts:fields.email"),
  enableSorting: false,
  cell: ({ row }) => {
    const value = primaryEmail(row.original);
    return value ? <span className="text-sm">{value}</span> : MUTED_DASH;
  },
};

const phoneColumn: ColumnDef<ContactListItem> = {
  id: "primary_phone",
  header: () => i18n.t("contacts:fields.phone"),
  enableSorting: false,
  cell: ({ row }) => {
    const value = primaryPhone(row.original);
    return value ? <span className="text-sm">{value}</span> : MUTED_DASH;
  },
};

const statusColumn: ColumnDef<ContactListItem> = {
  accessorKey: "status",
  header: () => i18n.t("contacts:fields.status"),
  enableSorting: false,
  cell: ({ getValue }) => {
    const value = getValue<string | null | undefined>();
    return value ? <StatusBadge status={value} /> : MUTED_DASH;
  },
};

export const contactColumns: ColumnDef<ContactListItem>[] = [
  nameColumn,
  kindColumn,
  agencyColumn,
  emailColumn,
  phoneColumn,
  statusColumn,
];

// GAP-048: the Suppliers directory is kind=CONTACT-scoped, so the kind column is
// redundant; it swaps in a property-role column instead.
export const supplierColumns: ColumnDef<ContactListItem>[] = [
  nameColumn,
  roleColumn,
  agencyColumn,
  emailColumn,
  phoneColumn,
  statusColumn,
];
