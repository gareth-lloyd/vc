import { TemplateEditorForm } from "../components/TemplateEditorForm";
import { useEmailTemplateContext } from "../outletContext";

export function EditTab() {
  const { template } = useEmailTemplateContext();
  return <TemplateEditorForm mode="edit" template={template} />;
}
