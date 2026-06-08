import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api/errors";
import { useEmailTemplate } from "./hooks";
import type { EmailTemplateOutletContext } from "./outletContext";

const TABS = [
  { slug: "edit", labelKey: "email_templates.tabs.edit" },
  { slug: "versions", labelKey: "email_templates.tabs.versions" },
] as const;

export function EmailTemplateDetailLayout() {
  const { t } = useTranslation("admin");
  const { key } = useParams<{ key: string }>();
  const query = useEmailTemplate(key);

  if (query.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    const is404 = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="p-6">
        <ErrorState
          title={
            is404
              ? t("email_templates.detail.not_found_title")
              : t("email_templates.detail.load_failed_title")
          }
          description={
            is404
              ? t("email_templates.detail.not_found_body")
              : t("email_templates.detail.load_failed_body")
          }
          onRetry={is404 ? undefined : () => query.refetch()}
        />
      </div>
    );
  }

  const template = query.data;

  return (
    <div>
      <PageHeader
        title={template.title}
        subtitle={
          <span className="flex items-center gap-2">
            <code className="font-mono text-xs">{template.key}</code>
            <span>{t("email_templates.detail.version_label", { version: template.version })}</span>
          </span>
        }
        breadcrumbs={[
          { label: t("email_templates.detail.breadcrumb"), to: "/admin/email-templates" },
          { label: template.title },
        ]}
        actions={template.is_active ? <StatusBadge status="active" /> : undefined}
      />

      <div className="border-border border-b px-6">
        <nav className="flex gap-1" aria-label={t("email_templates.tabs.edit")}>
          {TABS.map((tab) => (
            <NavLink
              key={tab.slug}
              to={tab.slug}
              className={({ isActive }) =>
                cn(
                  "border-b-2 px-3 py-2 text-sm font-medium",
                  isActive
                    ? "border-foreground text-foreground"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )
              }
            >
              {t(tab.labelKey)}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="p-6">
        <Outlet context={{ template } satisfies EmailTemplateOutletContext} />
      </div>
    </div>
  );
}
