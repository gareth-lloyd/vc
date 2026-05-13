import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/layout/PageHeader";

interface AdminPageShellProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function AdminPageShell({ title, description, actions, children }: AdminPageShellProps) {
  const { t } = useTranslation("admin");
  return (
    <div>
      <PageHeader
        title={title}
        subtitle={description}
        breadcrumbs={[{ label: t("common.breadcrumb_root") }, { label: title }]}
        actions={actions}
      />
      <div className="space-y-4 p-6">{children}</div>
    </div>
  );
}
