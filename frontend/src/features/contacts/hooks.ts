import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { queryKeys, type ContactId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  createContact,
  createContactEmail,
  createContactPhone,
  createContactRelationship,
  deleteContact,
  deleteContactEmail,
  deleteContactPhone,
  deleteContactRelationship,
  fetchContact,
  fetchContactBookings,
  fetchContactEnquiries,
  fetchContactProperties,
  fetchContactRelationships,
  fetchContacts,
  searchContacts,
  setPrimaryContactEmail,
  setPrimaryContactPhone,
  updateContact,
  updateContactEmail,
  updateContactPhone,
} from "./api";
import type {
  Contact,
  ContactCreateBody,
  ContactEmailWriteInput,
  ContactFilters,
  ContactPhoneWriteInput,
  ContactWriteInput,
  RelationshipWriteInput,
} from "./schemas";

export function useContacts(filters: ContactFilters) {
  return useQuery({
    queryKey: queryKeys.contacts.list(filters),
    queryFn: () => fetchContacts(filters),
  });
}

export function useContact(id: ContactId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.contacts.detail, fetchContact));
}

export function useContactProperties(id: ContactId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.contacts.properties, fetchContactProperties));
}

export function useContactEnquiries(id: ContactId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.contacts.enquiries, fetchContactEnquiries));
}

export function useContactBookings(id: ContactId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.contacts.bookings, fetchContactBookings));
}

export function useContactRelationships(id: ContactId | undefined) {
  return useQuery(enabledQuery(id, queryKeys.contacts.relationships, fetchContactRelationships));
}

export function useCreateContactRelationship(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RelationshipWriteInput) => createContactRelationship(contactId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.contacts.relationships(contactId),
      });
    },
  });
}

export function useDeleteContactRelationship(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ relId }: { relId: number }) => deleteContactRelationship(contactId, relId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.contacts.relationships(contactId),
      });
    },
  });
}

export function useSearchContacts(
  query: string,
  opts?: { kind?: "contact" | "customer"; status?: string },
) {
  return useQuery({
    queryKey: queryKeys.contacts.search(query, opts?.kind ?? "contact", opts?.status),
    queryFn: () => searchContacts(query, opts),
    enabled: query.length >= 2,
  });
}

// A contact's emails/phones/primary_* and name all appear on list rows
// (contactListItemSchema), so any contact write must refresh the list, not just
// the detail — otherwise the list and contact pickers go stale.
function invalidateContact(queryClient: QueryClient, contactId: ContactId) {
  queryClient.invalidateQueries({ queryKey: queryKeys.contacts.detail(contactId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.contacts.lists() });
}

export function useCreateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContactCreateBody) => createContact(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.lists() });
    },
  });
}

export function useUpdateContact(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<ContactWriteInput>) => updateContact(contactId, input),
    onSuccess: () => invalidateContact(queryClient, contactId),
  });
}

/**
 * GAP-053: optimistic tag setter for the inline editor. Each toggle PATCHes the
 * whole `tags` set and updates the contact-detail cache immediately. The
 * `cancelQueries` in onMutate is load-bearing — it kills the in-flight refetch
 * a prior toggle's onSettled dispatched, so a rapid second toggle can't be
 * clobbered by a stale refetch resolving late. onError rolls back to the
 * snapshot (the component surfaces the toast for i18n).
 */
export function useSetContactTags(contactId: ContactId) {
  const queryClient = useQueryClient();
  const key = queryKeys.contacts.detail(contactId);
  return useMutation<Contact, Error, string[], { snapshot: Contact | undefined }>({
    mutationFn: (tags) => updateContact(contactId, { tags }),
    onMutate: async (tags) => {
      await queryClient.cancelQueries({ queryKey: key });
      const snapshot = queryClient.getQueryData<Contact>(key);
      if (snapshot) queryClient.setQueryData<Contact>(key, { ...snapshot, tags });
      return { snapshot };
    },
    onError: (_err, _tags, ctx) => {
      if (ctx?.snapshot) queryClient.setQueryData(key, ctx.snapshot);
    },
    onSettled: () => invalidateContact(queryClient, contactId),
  });
}

export function useDeleteContact(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteContact(contactId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.lists() });
    },
  });
}

export function useCreateContactEmail(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContactEmailWriteInput) => createContactEmail(contactId, input),
    onSuccess: () => invalidateContact(queryClient, contactId),
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
    onSuccess: () => invalidateContact(queryClient, contactId),
  });
}

export function useDeleteContactEmail(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ emailId }: { emailId: number }) => deleteContactEmail(contactId, emailId),
    onSuccess: () => invalidateContact(queryClient, contactId),
  });
}

export function useSetPrimaryContactEmail(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ emailId }: { emailId: number }) => setPrimaryContactEmail(contactId, emailId),
    onSuccess: () => invalidateContact(queryClient, contactId),
  });
}

export function useCreateContactPhone(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContactPhoneWriteInput) => createContactPhone(contactId, input),
    onSuccess: () => invalidateContact(queryClient, contactId),
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
    onSuccess: () => invalidateContact(queryClient, contactId),
  });
}

export function useDeleteContactPhone(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ phoneId }: { phoneId: number }) => deleteContactPhone(contactId, phoneId),
    onSuccess: () => invalidateContact(queryClient, contactId),
  });
}

export function useSetPrimaryContactPhone(contactId: ContactId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ phoneId }: { phoneId: number }) => setPrimaryContactPhone(contactId, phoneId),
    onSuccess: () => invalidateContact(queryClient, contactId),
  });
}
