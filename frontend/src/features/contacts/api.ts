import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { ContactId } from "@/lib/query/keys";
import { z } from "zod";
import {
  contactBookingHistoryResponseSchema,
  contactEmailSchema,
  contactEnquiryHistoryResponseSchema,
  contactPhoneSchema,
  contactPropertyAssignmentSchema,
  contactSchema,
  contactsListResponseSchema,
  linkedContactSchema,
  linkedContactsResponseSchema,
  type Contact,
  type ContactCreateBody,
  type ContactEmail,
  type ContactEmailWriteInput,
  type ContactBookingHistoryItem,
  type ContactEnquiryHistoryItem,
  type ContactFilters,
  type ContactListItem,
  type ContactPhone,
  type ContactPhoneWriteInput,
  type ContactPropertyAssignment,
  type ContactWriteInput,
  type LinkedContact,
  type RelationshipWriteInput,
} from "./schemas";
import { paginated } from "@/lib/api/pagination";

function toQuery(filters: ContactFilters): QueryParams {
  return {
    q: filters.q || undefined,
    status: filters.status || undefined,
    kind: filters.kind || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchContacts(filters: ContactFilters): Promise<Paginated<ContactListItem>> {
  const data = await apiGet<unknown>("/contacts", { query: toQuery(filters) });
  return contactsListResponseSchema.parse(data);
}

export async function fetchContact(id: ContactId): Promise<Contact> {
  const data = await apiGet<unknown>(`/contacts/${id}`);
  return contactSchema.parse(data);
}

export async function fetchContactProperties(
  contactId: ContactId,
): Promise<ContactPropertyAssignment[]> {
  const data = await apiGet<unknown>(`/contacts/${contactId}/properties`);
  return z.array(contactPropertyAssignmentSchema).parse(data);
}

export async function fetchContactEnquiries(
  contactId: ContactId,
): Promise<Paginated<ContactEnquiryHistoryItem>> {
  const data = await apiGet<unknown>(`/contacts/${contactId}/enquiries`);
  return contactEnquiryHistoryResponseSchema.parse(data);
}

export async function fetchContactBookings(
  contactId: ContactId,
): Promise<Paginated<ContactBookingHistoryItem>> {
  const data = await apiGet<unknown>(`/contacts/${contactId}/bookings`);
  return contactBookingHistoryResponseSchema.parse(data);
}

export async function fetchContactRelationships(
  contactId: ContactId,
): Promise<Paginated<LinkedContact>> {
  const data = await apiGet<unknown>(`/contacts/${contactId}/relationships`);
  return linkedContactsResponseSchema.parse(data);
}

export async function createContactRelationship(
  contactId: ContactId,
  body: RelationshipWriteInput,
): Promise<LinkedContact> {
  const data = await apiSend<unknown>("POST", `/contacts/${contactId}/relationships`, body);
  return linkedContactSchema.parse(data);
}

export async function deleteContactRelationship(
  contactId: ContactId,
  relId: number,
): Promise<void> {
  await apiSend<void>("DELETE", `/contacts/${contactId}/relationships/${relId}`);
}

export async function searchContacts(
  query: string,
  opts?: { kind?: "contact" | "customer"; status?: string },
): Promise<Paginated<Contact>> {
  // GAP-045 D2: `/contacts` now includes customer Persons. Callers scope the
  // directory by `kind`: the property-assignment picker keeps the default
  // `kind=contact` (never a customer mirror); the enquiry picker passes
  // `kind=customer` (+ `status=active` GDPR floor) to offer linkable clients.
  const kind = opts?.kind ?? "contact";
  const data = await apiGet<unknown>("/contacts", {
    query: { q: query, kind, ...(opts?.status ? { status: opts.status } : {}) },
  });
  return paginated(contactSchema).parse(data);
}

export async function createContact(body: ContactCreateBody): Promise<Contact> {
  const data = await apiSend<unknown>("POST", "/contacts", body);
  return contactSchema.parse(data);
}

export async function updateContact(
  contactId: ContactId,
  body: Partial<ContactWriteInput>,
): Promise<Contact> {
  const data = await apiSend<unknown>("PATCH", `/contacts/${contactId}`, body);
  return contactSchema.parse(data);
}

export async function deleteContact(contactId: ContactId): Promise<void> {
  await apiSend<void>("DELETE", `/contacts/${contactId}`);
}

export async function createContactEmail(
  contactId: ContactId,
  body: ContactEmailWriteInput,
): Promise<ContactEmail> {
  const data = await apiSend<unknown>("POST", `/contacts/${contactId}/emails`, body);
  return contactEmailSchema.parse(data);
}

export async function updateContactEmail(
  contactId: ContactId,
  emailId: number,
  body: Partial<ContactEmailWriteInput>,
): Promise<ContactEmail> {
  const data = await apiSend<unknown>("PATCH", `/contacts/${contactId}/emails/${emailId}`, body);
  return contactEmailSchema.parse(data);
}

export async function deleteContactEmail(contactId: ContactId, emailId: number): Promise<void> {
  await apiSend<void>("DELETE", `/contacts/${contactId}/emails/${emailId}`);
}

export async function setPrimaryContactEmail(
  contactId: ContactId,
  emailId: number,
): Promise<ContactEmail> {
  const data = await apiSend<unknown>(
    "POST",
    `/contacts/${contactId}/emails/${emailId}:set-primary`,
  );
  return contactEmailSchema.parse(data);
}

export async function createContactPhone(
  contactId: ContactId,
  body: ContactPhoneWriteInput,
): Promise<ContactPhone> {
  const data = await apiSend<unknown>("POST", `/contacts/${contactId}/phones`, body);
  return contactPhoneSchema.parse(data);
}

export async function updateContactPhone(
  contactId: ContactId,
  phoneId: number,
  body: Partial<ContactPhoneWriteInput>,
): Promise<ContactPhone> {
  const data = await apiSend<unknown>("PATCH", `/contacts/${contactId}/phones/${phoneId}`, body);
  return contactPhoneSchema.parse(data);
}

export async function deleteContactPhone(contactId: ContactId, phoneId: number): Promise<void> {
  await apiSend<void>("DELETE", `/contacts/${contactId}/phones/${phoneId}`);
}

export async function setPrimaryContactPhone(
  contactId: ContactId,
  phoneId: number,
): Promise<ContactPhone> {
  const data = await apiSend<unknown>(
    "POST",
    `/contacts/${contactId}/phones/${phoneId}:set-primary`,
  );
  return contactPhoneSchema.parse(data);
}
