import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { ColumnDef } from "@tanstack/react-table";
import { StatusBadge } from "@/components/data/StatusBadge";
import { formatDate } from "@/lib/format/date";
import { LeadStatusCell } from "./components/LeadStatusCell";
import { enquirySourceLabel, enquiryStatusLabel, type EnquiryListItem } from "./schemas";

const MUTED_DASH = <span className="text-muted-foreground">—</span>;

/**
 * Maps the stored flexibility shape to the Flex? cell. The structured spread is
 * capped at 0–3 today (the `± 7 days` variant arrives with GAP-043), so this is
 * an interim three-way label: a positive spread → `± N days`; otherwise the
 * open-ended `is_flexible` flag → `Flexible`; else fixed `Specific dates`.
 */
function flexLabel(t: TFunction<"enquiries">, isFlexible: boolean, days: number): string {
  if (days > 0) return t("columns.flex.spread", { count: days });
  if (isFlexible) return t("columns.flex.flexible");
  return t("columns.flex.specific");
}

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
        id: "region",
        header: t("columns.region"),
        enableSorting: false,
        cell: ({ row }) => {
          const name = row.original.region_name;
          if (name) return <span className="text-sm">{name}</span>;
          if (row.original.region != null) {
            return <span className="text-muted-foreground text-sm">#{row.original.region}</span>;
          }
          return MUTED_DASH;
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
        id: "flex",
        header: t("columns.flex.header"),
        enableSorting: false,
        cell: ({ row }) => (
          <span className="text-sm">
            {flexLabel(t, row.original.is_flexible, row.original.flexibility_days)}
          </span>
        ),
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
        id: "assigned_to",
        header: t("columns.sales_person"),
        enableSorting: false,
        cell: ({ row }) => {
          const name = row.original.assigned_to_name;
          if (name) return <span className="text-sm">{name}</span>;
          if (row.original.assigned_to != null) {
            return (
              <span className="text-muted-foreground text-sm">#{row.original.assigned_to}</span>
            );
          }
          return <span className="text-muted-foreground text-sm">{t("columns.unassigned")}</span>;
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
        accessorKey: "lead_status",
        header: t("columns.lead_status"),
        enableSorting: false,
        cell: ({ row }) => (
          <LeadStatusCell
            enquiryId={row.original.id}
            reference={row.original.reference}
            value={row.original.lead_status}
          />
        ),
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
