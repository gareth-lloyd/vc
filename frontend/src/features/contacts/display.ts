import i18n from "@/i18n";
import type { Contact } from "./schemas";

export function contactDisplayName(contact: Contact): string {
  const full = [contact.first_name, contact.last_name].filter(Boolean).join(" ").trim();
  if (full) return full;
  if (contact.agency_detail?.name) return contact.agency_detail.name;
  return i18n.t("contacts:fallback.name_with_id", { id: contact.id });
}

/**
 * GAP-053: a contact is a "client" — eligible for customer tags — when it has
 * customer or agent capacity, i.e. it appears in the Clients directory. The
 * derived `contact_types` already encodes both (customer = kind/bookings,
 * agent = agency), mirroring the backend membership. Pure deal-channel agents
 * with no agency are deferred (they won't surface as clients here).
 */
export function isClientContact(contact: Contact): boolean {
  return (contact.contact_types ?? []).some((type) => type === "customer" || type === "agent");
}
