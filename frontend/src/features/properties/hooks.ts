import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys, type ContactId, type PropertyId, type SeasonId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  createContact,
  createContactEmail,
  createContactPhone,
  createPropertyContact,
  deleteContactEmail,
  deleteContactPhone,
  deletePropertyContact,
  fetchContact,
  fetchProperties,
  fetchProperty,
  fetchPropertyBookingsForRange,
  fetchPropertyContacts,
  fetchPropertyDescriptions,
  fetchPropertyDiscounts,
  fetchPropertyExtras,
  fetchPropertyFeatures,
  fetchPropertyHolds,
  fetchPropertyRooms,
  fetchPropertySeasons,
  fetchSeasonDetail,
  searchContacts,
  setPrimaryContactEmail,
  setPrimaryContactPhone,
  updateContact,
  updateContactEmail,
  updateContactPhone,
  updatePropertyContact,
} from "./api";
import type {
  ContactEmailWriteInput,
  ContactPhoneWriteInput,
  ContactWriteInput,
  PropertyContactAssignmentWriteInput,
  PropertyFilters,
} from "./schemas";

export const PROPERTIES_PAGE_SIZE = 50;

export function useProperties(filters: PropertyFilters) {
  return useQuery({
    queryKey: queryKeys.properties.list(filters),
    queryFn: () => fetchProperties(filters),
  });
}

export function useProperty(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.detail, fetchProperty));
}

export function usePropertyDescriptions(idOrSlug: PropertyId | undefined) {
  return useQuery(
    enabledQuery(idOrSlug, queryKeys.properties.descriptions, fetchPropertyDescriptions),
  );
}

export function usePropertyFeatures(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.features, fetchPropertyFeatures));
}

export function usePropertyRooms(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.rooms, fetchPropertyRooms));
}

export function usePropertySeasons(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.seasons, fetchPropertySeasons));
}

export function useSeasonDetail(seasonId: SeasonId | undefined) {
  return useQuery(enabledQuery(seasonId, queryKeys.properties.seasonDetail, fetchSeasonDetail));
}

export function usePropertyExtras(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.extras, fetchPropertyExtras));
}

export function usePropertyDiscounts(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.discounts, fetchPropertyDiscounts));
}

export function usePropertyContacts(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.contacts, fetchPropertyContacts));
}

export function useContact(id: ContactId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.contacts.detail, fetchContact));
}

export function usePropertyHolds(propertyId: number | undefined, from: string, to: string) {
  return useQuery({
    queryKey: queryKeys.properties.holds(propertyId!, from, to),
    queryFn: () => fetchPropertyHolds(propertyId!, from, to),
    enabled: propertyId != null,
  });
}

export function usePropertyBookingsForRange(
  propertyId: number | undefined,
  from: string,
  to: string,
) {
  return useQuery({
    queryKey: queryKeys.properties.bookingsInRange(propertyId!, from, to),
    queryFn: () => fetchPropertyBookingsForRange(propertyId!, from, to),
    enabled: propertyId != null,
  });
}

export function useSearchContacts(query: string) {
  return useQuery({
    queryKey: queryKeys.contacts.search(query),
    queryFn: () => searchContacts(query),
    enabled: query.length >= 2,
  });
}

export function useCreatePropertyContact(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyContactAssignmentWriteInput) =>
      createPropertyContact(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.contacts(propertyId) });
    },
  });
}

interface UpdatePropertyContactVars {
  mappingId: number;
  input: Partial<PropertyContactAssignmentWriteInput>;
}

export function useUpdatePropertyContact(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ mappingId, input }: UpdatePropertyContactVars) =>
      updatePropertyContact(propertyId, mappingId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.contacts(propertyId) });
    },
  });
}

export function useDeletePropertyContact(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ mappingId }: { mappingId: number }) =>
      deletePropertyContact(propertyId, mappingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.contacts(propertyId) });
    },
  });
}

export function useCreateContactEmail(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContactEmailWriteInput) => createContactEmail(contactId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

interface UpdateContactEmailVars {
  emailId: number;
  input: Partial<ContactEmailWriteInput>;
}

export function useUpdateContactEmail(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ emailId, input }: UpdateContactEmailVars) =>
      updateContactEmail(contactId, emailId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

export function useDeleteContactEmail(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ emailId }: { emailId: number }) => deleteContactEmail(contactId, emailId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

export function useSetPrimaryContactEmail(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ emailId }: { emailId: number }) => setPrimaryContactEmail(contactId, emailId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

export function useCreateContactPhone(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContactPhoneWriteInput) => createContactPhone(contactId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

interface UpdateContactPhoneVars {
  phoneId: number;
  input: Partial<ContactPhoneWriteInput>;
}

export function useUpdateContactPhone(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ phoneId, input }: UpdateContactPhoneVars) =>
      updateContactPhone(contactId, phoneId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

export function useDeleteContactPhone(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ phoneId }: { phoneId: number }) => deleteContactPhone(contactId, phoneId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

export function useSetPrimaryContactPhone(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ phoneId }: { phoneId: number }) => setPrimaryContactPhone(contactId, phoneId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}

export function useCreateContact() {
  return useMutation({
    mutationFn: (input: ContactWriteInput) => createContact(input),
  });
}

export function useUpdateContact(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<ContactWriteInput>) => updateContact(contactId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
    },
  });
}
