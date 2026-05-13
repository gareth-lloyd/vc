import type { Contact } from "./schemas";

export function contactDisplayName(contact: Contact): string {
  const full = [contact.first_name, contact.last_name].filter(Boolean).join(" ").trim();
  if (full) return full;
  if (contact.company) return contact.company;
  return `Contact #${contact.id}`;
}
