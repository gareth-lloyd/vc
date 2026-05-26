import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ColumnDef } from "@tanstack/react-table";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import { enquirySourceLabel, enquiryStatusLabel, type EnquiryListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

export function useEnquiryColumns(): ColumnDef<EnquiryListItem>[] {
  const { t } = useTranslation("enquiries");
  return useMemo<ColumnDef<EnquiryListItem>[]>(
    () => [
      {
        accessorKey: "reference",
        header: t("columns.ref"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-foreground font-mono text-sm">{row.original.reference}</span>
        ),
      },
      {
        id: "guest",
        header: t("columns.guest"),
        enableSorting: false,
        cell: ({ row }) => {
          const denorm = `${row.original.first_name ?? ""} ${row.original.last_name ?? ""}`.trim();
          const name =
            row.original.guest_name || denorm || row.original.email || t("columns.unknown_guest");
          return (
            <div className="text-sm">
              <div>{name}</div>
              {row.original.email && row.original.email !== name ? (
                <div className="text-muted-foreground text-xs">{row.original.email}</div>
              ) : null}
            </div>
          );
        },
      },
      {
        id: "property",
        header: t("columns.property"),
        enableSorting: false,
        cell: ({ row }) => {
          const name = row.original.property_name;
          if (name) return <span className="text-sm">{name}</span>;
          if (row.original.property != null) {
            return <span className="text-muted-foreground text-sm">#{row.original.property}</span>;
          }
          return <span className="text-muted-foreground text-sm">{t("columns.no_property")}</span>;
        },
      },
      {
        accessorKey: "date_from",
        header: t("columns.dates"),
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
        header: t("columns.party"),
        enableSorting: false,
        cell: ({ row }) => {
          const { adults, children } = row.original;
          const party = children
            ? t("detail.rail.party_format_with_children", { adults, children })
            : t("detail.rail.party_format", { adults });
          return <span className="text-sm">{party}</span>;
        },
      },
      {
        accessorKey: "site_source",
        header: t("columns.source"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-sm">{enquirySourceLabel(row.original.site_source)}</span>
        ),
      },
      {
        accessorKey: "status",
        header: t("columns.status"),
        enableSorting: true,
        cell: ({ row }) => <StatusBadge status={enquiryStatusLabel(row.original.status)} />,
      },
      {
        accessorKey: "created_at",
        header: t("columns.created"),
        enableSorting: true,
        cell: ({ row }) => (
          <span className="text-sm">{formatDate(row.original.created_at ?? null)}</span>
        ),
      },
    ],
    [t],
  );
}
