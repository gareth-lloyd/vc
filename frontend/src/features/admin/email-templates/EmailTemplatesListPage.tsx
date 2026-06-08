import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AdminPageShell } from "@/features/admin/components/AdminPageShell";
import { DataTable } from "@/components/data/DataTable";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useHasAdminRole } from "@/lib/auth/useHasAdminRole";
import { useEmailTemplates } from "./hooks";
import { emailTemplateColumns } from "./columns";

// The active-template catalogue is a handful of rows, so there's no search or
// pagination here (the `?key=` API filter is exact-match, which would be a
// confusing "search"). We list every active template and click through to edit.
export function EmailTemplatesListPage() {
  const { t } = useTranslation("admin");
  const navigate = useNavigate();
  const canWrite = useHasAdminRole();
  const query = useEmailTemplates({});
  const columns = useMemo(() => emailTemplateColumns(t), [t]);

  return (
    <AdminPageShell
      title={t("email_templates.title")}
      description={t("email_templates.description")}
      actions={
        <Button
          size="sm"
          onClick={() => navigate("/admin/email-templates/new")}
          disabled={!canWrite}
        >
          {t("email_templates.new_button")}
        </Button>
      }
    >
      {query.isError ? (
        <ErrorState
          description={t("email_templates.errors.load_failed")}
          onRetry={() => query.refetch()}
          retrying={query.isFetching}
        />
      ) : (
        <DataTable
          columns={columns}
          data={query.data?.results}
          isLoading={query.isLoading}
          pageIndex={0}
          pageCount={1}
          pageSize={query.data?.results.length ?? 0}
          sorting={[]}
          onSortingChange={() => {}}
          onPageChange={() => {}}
          onRowClick={(row) => navigate(`/admin/email-templates/${encodeURIComponent(row.key)}`)}
          rowKey={(row) => row.key}
          emptyContent={
            <EmptyState
              title={t("email_templates.empty.title")}
              description={t("email_templates.empty.description")}
            />
          }
        />
      )}
    </AdminPageShell>
  );
}
