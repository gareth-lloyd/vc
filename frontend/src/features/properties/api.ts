import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import { paginated } from "@/lib/api/pagination";
import {
  availabilityHoldsResponseSchema,
  contactSchema,
  type ContactEmailWriteInput,
  type ContactPhoneWriteInput,
  type ContactWriteInput,
  discountsResponseSchema,
  extrasResponseSchema,
  propertyBookingsResponseSchema,
  propertyContactsResponseSchema,
  propertyDescriptionsResponseSchema,
  propertyDetailSchema,
  propertyFeaturesResponseSchema,
  propertyListResponseSchema,
  propertyRoomsResponseSchema,
  ratePlanDetailSchema,
  ratePlansResponseSchema,
  type AvailabilityHold,
  type Contact,
  type ContactEmail,
  type ContactPhone,
  contactEmailSchema,
  contactPhoneSchema,
  type Discount,
  type Extra,
  type PropertyBookingItem,
  type PropertyContactAssignment,
  propertyContactAssignmentSchema,
  type PropertyContactAssignmentWriteInput,
  type PropertyDescription,
  type PropertyDetail,
  type PropertyFeature,
  type PropertyFilters,
  type PropertyListItem,
  type PropertyRoom,
  type RatePlan,
  type RatePlanDetail,
} from "./schemas";
import type { Paginated } from "@/types/api";
import type { ContactId, PropertyId, SeasonId } from "@/lib/query/keys";

function toQuery(filters: PropertyFilters): QueryParams {
  return {
    q: filters.q || undefined,
    country: filters.country || undefined,
    status: filters.status || undefined,
    ordering: filters.ordering || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchProperties(
  filters: PropertyFilters,
): Promise<Paginated<PropertyListItem>> {
  const data = await apiGet<unknown>("/properties", { query: toQuery(filters) });
  return propertyListResponseSchema.parse(data);
}

export async function fetchProperty(idOrSlug: PropertyId): Promise<PropertyDetail> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}`);
  return propertyDetailSchema.parse(data);
}

export async function fetchPropertyDescriptions(
  idOrSlug: PropertyId,
): Promise<Paginated<PropertyDescription>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/descriptions`);
  return propertyDescriptionsResponseSchema.parse(data);
}

export async function fetchPropertyFeatures(
  idOrSlug: PropertyId,
): Promise<Paginated<PropertyFeature>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/features`);
  return propertyFeaturesResponseSchema.parse(data);
}

export async function fetchPropertyRooms(idOrSlug: PropertyId): Promise<Paginated<PropertyRoom>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/rooms`);
  return propertyRoomsResponseSchema.parse(data);
}

export async function fetchPropertySeasons(idOrSlug: PropertyId): Promise<Paginated<RatePlan>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/seasons`);
  return ratePlansResponseSchema.parse(data);
}

export async function fetchSeasonDetail(seasonId: SeasonId): Promise<RatePlanDetail> {
  const data = await apiGet<unknown>(`/seasons/${seasonId}`);
  return ratePlanDetailSchema.parse(data);
}

export async function fetchPropertyExtras(idOrSlug: PropertyId): Promise<Paginated<Extra>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/extras`);
  return extrasResponseSchema.parse(data);
}

export async function fetchPropertyDiscounts(idOrSlug: PropertyId): Promise<Paginated<Discount>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/discounts`);
  return discountsResponseSchema.parse(data);
}

export async function fetchPropertyContacts(
  idOrSlug: PropertyId,
): Promise<Paginated<PropertyContactAssignment>> {
  const data = await apiGet<unknown>(`/properties/${idOrSlug}/contacts`);
  return propertyContactsResponseSchema.parse(data);
}

export async function fetchContact(id: ContactId): Promise<Contact> {
  const data = await apiGet<unknown>(`/contacts/${id}`);
  return contactSchema.parse(data);
}

export async function fetchPropertyHolds(
  propertyId: number,
  from: string,
  to: string,
): Promise<AvailabilityHold[]> {
  const data = await apiGet<unknown>("/availability", {
    query: { property_ids: propertyId, from, to },
  });
  return availabilityHoldsResponseSchema.parse(data).records;
}

export async function fetchPropertyBookingsForRange(
  propertyId: number,
  from: string,
  to: string,
): Promise<Paginated<PropertyBookingItem>> {
  const data = await apiGet<unknown>("/bookings", {
    query: { property: propertyId, check_in_before: to, check_out_after: from },
  });
  return propertyBookingsResponseSchema.parse(data);
}

export async function searchContacts(query: string): Promise<Paginated<Contact>> {
  const data = await apiGet<unknown>("/contacts", { query: { q: query } });
  return paginated(contactSchema).parse(data);
}

export async function createPropertyContact(
  propertyId: PropertyId,
  body: PropertyContactAssignmentWriteInput,
): Promise<PropertyContactAssignment> {
  const data = await apiSend<unknown>("POST", `/properties/${propertyId}/contacts`, body);
  return propertyContactAssignmentSchema.parse(data);
}

export async function updatePropertyContact(
  propertyId: PropertyId,
  mappingId: number,
  body: Partial<PropertyContactAssignmentWriteInput>,
): Promise<PropertyContactAssignment> {
  const data = await apiSend<unknown>(
    "PATCH",
    `/properties/${propertyId}/contacts/${mappingId}`,
    body,
  );
  return propertyContactAssignmentSchema.parse(data);
}

export async function deletePropertyContact(
  propertyId: PropertyId,
  mappingId: number,
): Promise<void> {
  await apiSend<void>("DELETE", `/properties/${propertyId}/contacts/${mappingId}`);
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

export async function createContact(body: ContactWriteInput): Promise<Contact> {
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
