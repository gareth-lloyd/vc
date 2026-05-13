import { useTranslation } from "react-i18next";
import { useNavigate, useOutletContext } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import i18n from "@/i18n";
import { DataTable } from "@/components/data/DataTable";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDate } from "@/lib/format/date";
import { useContactProperties } from "../hooks";
import type { ContactPropertyAssignment } from "../schemas";
import type { ContactOutletContext } from "../ContactDetailLayout";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

const columns: ColumnDef<ContactPropertyAssignment>[] = [
  {
    id: "property",
    header: () => i18n.t("contacts:fields.property"),
    enableSorting: false,
    cell: ({ row }) => {
      const { property_slug, property_id } = row.original;
      const label =
        property_slug && !property_slug.includes("/") ? property_slug : `#${property_id}`;
      return <span className="text-foreground font-medium">{label}</span>;
    },
  },
  {
    accessorKey: "role",
    header: () => i18n.t("contacts:fields.role"),
    enableSorting: false,
    cell: ({ getValue }) => {
      const value = getValue<string | null | undefined>();
      if (!value) return MUTED_DASH;
      return <span className="text-sm capitalize">{value.replace(/_/g, " ")}</span>;
    },
  },
  {
    accessorKey: "is_primary",
    header: () => i18n.t("contacts:fields.primary"),
    enableSorting: false,
    cell: ({ getValue }) =>
      getValue<boolean>() ? (
        <Badge variant="secondary">{i18n.t("common:status.primary")}</Badge>
      ) : (
        MUTED_DASH
      ),
  },
  {
    accessorKey: "start_date",
    header: () => i18n.t("contacts:fields.start"),
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="text-sm">{formatDate(getValue<string | null>())}</span>
    ),
  },
  {
    accessorKey: "end_date",
    header: () => i18n.t("contacts:fields.end"),
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="text-sm">{formatDate(getValue<string | null>())}</span>
    ),
  },
];

export function PropertiesTab() {
  const { t } = useTranslation("contacts");
  const { contact } = useOutletContext<ContactOutletContext>();
  const navigate = useNavigate();
  const query = useContactProperties(contact.id);

  if (query.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title={t("errors.load_properties_failed")}
          description={t("errors.load_properties_retry")}
          onRetry={() => query.refetch()}
        />
      </div>
    );
  }

  const rows = query.data ?? [];
  const handleRowClick = (row: ContactPropertyAssignment) => {
    const slug = row.property_slug?.trim();
    const isValidSlug = slug && !slug.includes("/");
    navigate(`/properties/${isValidSlug ? slug : row.property_id}`);
  };

  return (
    <div className="space-y-4 p-6">
      <h2 className="text-foreground text-lg font-semibold">
        {t("headings.property_assignments")}
      </h2>
      <DataTable
        columns={columns}
        data={rows}
        isLoading={query.isLoading}
        pageIndex={0}
        pageCount={1}
        sorting={[]}
        onSortingChange={() => {}}
        onPageChange={() => {}}
        onRowClick={handleRowClick}
        rowKey={(row) => row.id}
        emptyContent={<EmptyState title={t("empty.property_assignments")} />}
      />
    </div>
  );
}
