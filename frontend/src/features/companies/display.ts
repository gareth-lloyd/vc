import i18n from "@/i18n";
import type { Company, CompanyListItem } from "./schemas";

export function companyDisplayName(
  company: Pick<Company | CompanyListItem, "id" | "name">,
): string {
  if (company.name) return company.name;
  return i18n.t("companies:fallback.name_with_id", { id: company.id });
}
