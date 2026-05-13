import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys, type PropertyId, type SeasonId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  activateProperty,
  archiveProperty,
  createPropertyContact,
  createPropertyImage,
  deletePropertyContact,
  deletePropertyImage,
  fetchProperties,
  fetchProperty,
  fetchPropertyBookingsForRange,
  fetchPropertyContacts,
  fetchPropertyDescriptions,
  fetchPropertyDiscounts,
  fetchPropertyExtras,
  fetchPropertyFeatures,
  fetchPropertyFinance,
  fetchPropertyHolds,
  fetchPropertyImages,
  fetchPropertyRooms,
  fetchPropertySeasons,
  fetchPropertySettings,
  fetchSeasonDetail,
  reorderPropertyImages,
  restoreProperty,
  setPropertyImageHero,
  updatePropertyContact,
  updatePropertyFinance,
  updatePropertyImage,
  updatePropertySettings,
} from "./api";
import type {
  PropertyContactAssignmentWriteInput,
  PropertyFilters,
  PropertyFinanceWriteInput,
  PropertyImageWriteInput,
  PropertySettingsWriteInput,
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

export function usePropertyImages(propertyId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.properties.images(propertyId!),
    queryFn: () => fetchPropertyImages(propertyId!),
    enabled: propertyId != null,
  });
}

export function useCreatePropertyImage(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyImageWriteInput) => createPropertyImage(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.images(propertyId) });
    },
  });
}

interface UpdatePropertyImageVars {
  imageId: number;
  input: Partial<{
    kind: string;
    name: string;
    description: string;
    sort_order: number;
    is_active: boolean;
  }>;
}

export function useUpdatePropertyImage(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ imageId, input }: UpdatePropertyImageVars) =>
      updatePropertyImage(propertyId, imageId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.images(propertyId) });
    },
  });
}

export function useDeletePropertyImage(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ imageId }: { imageId: number }) => deletePropertyImage(propertyId, imageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.images(propertyId) });
    },
  });
}

export function useReorderPropertyImages(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (imageIds: number[]) => reorderPropertyImages(propertyId, imageIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.images(propertyId) });
    },
  });
}

export function useSetPropertyImageHero(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ imageId }: { imageId: number }) => setPropertyImageHero(propertyId, imageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.images(propertyId) });
    },
  });
}

export function usePropertySettings(propertyId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.properties.settings(propertyId!),
    queryFn: () => fetchPropertySettings(propertyId!),
    enabled: propertyId != null,
  });
}

export function useUpdatePropertySettings(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertySettingsWriteInput) => updatePropertySettings(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.settings(propertyId) });
    },
  });
}

export function usePropertyFinance(propertyId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.properties.finance(propertyId!),
    queryFn: () => fetchPropertyFinance(propertyId!),
    enabled: propertyId != null,
  });
}

export function useUpdatePropertyFinance(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyFinanceWriteInput) => updatePropertyFinance(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.finance(propertyId) });
    },
  });
}

function invalidatePropertyDetail(
  queryClient: ReturnType<typeof useQueryClient>,
  property: { id: number; slug?: string | null },
) {
  queryClient.invalidateQueries({ queryKey: queryKeys.properties.detail(property.id) });
  if (property.slug) {
    queryClient.invalidateQueries({ queryKey: queryKeys.properties.detail(property.slug) });
  }
  queryClient.invalidateQueries({ queryKey: queryKeys.properties.all() });
}

export function useActivateProperty(property: { id: number; slug?: string | null }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => activateProperty(property.id),
    onSuccess: () => invalidatePropertyDetail(queryClient, property),
  });
}

export function useArchiveProperty(property: { id: number; slug?: string | null }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => archiveProperty(property.id),
    onSuccess: () => invalidatePropertyDetail(queryClient, property),
  });
}

export function useRestoreProperty(property: { id: number; slug?: string | null }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => restoreProperty(property.id),
    onSuccess: () => invalidatePropertyDetail(queryClient, property),
  });
}
