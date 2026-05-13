import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
