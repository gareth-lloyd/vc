import i18n from "@/i18n";
import type { Contact } from "./schemas";

export function contactDisplayName(contact: Contact): string {
  const full = [contact.first_name, contact.last_name].filter(Boolean).join(" ").trim();
  if (full) return full;
  if (contact.agency_detail?.name) return contact.agency_detail.name;
  return i18n.t("contacts:fallback.name_with_id", { id: contact.id });
}
