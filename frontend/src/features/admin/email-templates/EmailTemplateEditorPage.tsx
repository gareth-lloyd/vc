import { useTranslation } from "react-i18next";
import { AdminPageShell } from "@/features/admin/components/AdminPageShell";
import { TemplateEditorForm } from "./components/TemplateEditorForm";

// The create surface, at `/admin/email-templates/new`. Create has no `key` yet,
// so it lives on its own route rather than in the key-addressed detail layout;
// on a successful publish the form navigates to the new template's detail.
export function EmailTemplateEditorPage() {
  const { t } = useTranslation("admin");
  return (
    <AdminPageShell title={t("email_templates.create.title")}>
      <TemplateEditorForm mode="create" />
    </AdminPageShell>
  );
}
