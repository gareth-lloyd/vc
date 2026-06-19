import type { Contact } from "./schemas";

/** The contact's primary email, falling back to the first listed, then "". */
export function primaryEmail(contact: Contact): string {
  return (contact.emails.find((e) => e.is_primary) ?? contact.emails[0])?.email ?? "";
}

/** The contact's primary phone, falling back to the first listed, then "". */
export function primaryPhone(contact: Contact): string {
  return (contact.phones.find((p) => p.is_primary) ?? contact.phones[0])?.number ?? "";
}
