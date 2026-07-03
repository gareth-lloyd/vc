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

/**
 * Contact-types that CAN hold a property (owners, managers, agents, and the
 * other business roles). Gates the Properties tab: a pure client — no such
 * type and no actual property link — has no properties to show, so the (empty)
 * tab is hidden. Mirrors the backend `ContactRole` values plus the synthetic
 * `agent` type (product decision: agents always get the tab).
 */
const PROPERTY_CAPABLE_TYPES = new Set([
  "owner",
  "manager",
  "villa_admin",
  "management_company",
  "housekeeper",
  "owners_rep",
  "agent",
]);

/**
 * True when the Properties tab should show: the contact either can hold
 * properties by type, or actually has ≥1 property assignment (active or
 * historical, via the server-derived `has_property_assignments`).
 */
export function contactCanHaveProperties(
  contact: Pick<Contact, "contact_types" | "has_property_assignments">,
): boolean {
  return (
    contact.has_property_assignments === true ||
    (contact.contact_types ?? []).some((type) => PROPERTY_CAPABLE_TYPES.has(type))
  );
}
