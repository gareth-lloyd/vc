import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { queryKeys, type ContactId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  createContact,
  createContactEmail,
  createContactPhone,
  deleteContact,
  deleteContactEmail,
  deleteContactPhone,
  fetchContact,
  fetchContactProperties,
  fetchContacts,
  searchContacts,
  setPrimaryContactEmail,
  setPrimaryContactPhone,
  updateContact,
  updateContactEmail,
  updateContactPhone,
} from "./api";
import type {
  ContactCreateBody,
  ContactEmailWriteInput,
  ContactFilters,
  ContactPhoneWriteInput,
  ContactWriteInput,
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

export function useSearchContacts(query: string) {
  return useQuery({
    queryKey: queryKeys.contacts.search(query),
    queryFn: () => searchContacts(query),
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
