import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import type { ContactId } from "@/lib/query/keys";
import { z } from "zod";
import {
  contactEmailSchema,
  contactPhoneSchema,
  contactPropertyAssignmentSchema,
  contactSchema,
  contactsListResponseSchema,
  type Contact,
  type ContactCreateBody,
  type ContactEmail,
  type ContactEmailWriteInput,
  type ContactFilters,
  type ContactListItem,
  type ContactPhone,
  type ContactPhoneWriteInput,
  type ContactPropertyAssignment,
  type ContactWriteInput,
} from "./schemas";
import { paginated } from "@/lib/api/pagination";

function toQuery(filters: ContactFilters): QueryParams {
  return {
    q: filters.q || undefined,
    status: filters.status || undefined,
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

export async function searchContacts(query: string): Promise<Paginated<Contact>> {
  const data = await apiGet<unknown>("/contacts", { query: { q: query } });
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
