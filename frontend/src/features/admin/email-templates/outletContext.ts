import { useOutletContext } from "react-router-dom";
import type { EmailTemplateDetail } from "./schemas";

export interface EmailTemplateOutletContext {
  template: EmailTemplateDetail;
}

// Tabs (`EditTab`, `VersionsTab`) read the loaded active template from the
// detail layout's router outlet context.
export function useEmailTemplateContext(): EmailTemplateOutletContext {
  return useOutletContext<EmailTemplateOutletContext>();
}
