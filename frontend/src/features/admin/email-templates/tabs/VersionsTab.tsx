import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useTranslation } from "react-i18next";
import { DataTable } from "@/components/data/DataTable";
import { StatusBadge } from "@/components/data/StatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { formatDateTime } from "@/lib/format/date";
import { PreviewPane } from "../components/PreviewPane";
import { useEmailTemplateVersions } from "../hooks";
import { useEmailTemplateContext } from "../outletContext";
import type { EmailTemplateDetail } from "../schemas";

// The versions endpoint returns full detail objects (bodies included), so the
// read-only view renders straight from the selected row — no extra fetch.
function versionColumns(
  t: ReturnType<typeof useTranslation>["t"],
  onView: (v: EmailTemplateDetail) => void,
): ColumnDef<EmailTemplateDetail>[] {
  return [
    {
      accessorKey: "version",
      header: t("email_templates.versions.columns.version"),
      enableSorting: false,
      cell: ({ row }) => <span className="tabular-nums">v{row.original.version}</span>,
    },
    {
      accessorKey: "is_active",
      header: t("email_templates.versions.columns.is_active"),
      enableSorting: false,
      cell: ({ row }) =>
        row.original.is_active ? (
          <StatusBadge status="active" />
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      accessorKey: "updated_at",
      header: t("email_templates.versions.columns.updated_at"),
      enableSorting: false,
      cell: ({ row }) => <span className="text-sm">{formatDateTime(row.original.updated_at)}</span>,
    },
    {
      accessorKey: "notes",
      header: t("email_templates.versions.columns.notes"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-muted-foreground text-sm">{row.original.notes || "—"}</span>
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <Button variant="ghost" size="sm" onClick={() => onView(row.original)}>
          {t("email_templates.versions.view")}
        </Button>
      ),
    },
  ];
}

export function VersionsTab() {
  const { t } = useTranslation("admin");
  const { template } = useEmailTemplateContext();
  const query = useEmailTemplateVersions(template.key);
  const [selected, setSelected] = useState<EmailTemplateDetail | null>(null);
  const columns = useMemo(() => versionColumns(t, setSelected), [t]);

  if (query.isError) {
    return (
      <ErrorState
        description={t("email_templates.versions.error")}
        onRetry={() => query.refetch()}
        retrying={query.isFetching}
      />
    );
  }

  return (
    <>
      <DataTable
        columns={columns}
        data={query.data}
        isLoading={query.isLoading}
        pageIndex={0}
        pageCount={1}
        pageSize={query.data?.length ?? 0}
        sorting={[]}
        onSortingChange={() => {}}
        onPageChange={() => {}}
        rowKey={(row) => row.version}
        emptyContent={<EmptyState title={t("email_templates.versions.empty")} />}
      />

      <Dialog open={selected != null} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
          {selected ? (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {t("email_templates.versions.sheet_title", { version: selected.version })}
                  {selected.is_active ? <StatusBadge status="active" /> : null}
                </DialogTitle>
              </DialogHeader>
              <PreviewPane
                mode="static"
                subject={selected.subject_template}
                html={selected.body_template_html}
              />
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
