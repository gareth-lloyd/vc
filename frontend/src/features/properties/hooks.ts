import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { queryKeys, type PropertyId, type SeasonId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  activateProperty,
  archiveProperty,
  createChangeOverRule,
  createProperty,
  createPropertyBlock,
  createPropertyContact,
  createPropertyImage,
  createPropertyNearbyPlace,
  createPropertyRoom,
  createPropertyService,
  createRateCard,
  createRateRule,
  createSeason,
  deleteChangeOverRule,
  deletePropertyBlock,
  deletePropertyContact,
  deletePropertyDescription,
  deletePropertyImage,
  deletePropertyNearbyPlace,
  deletePropertyRoom,
  deletePropertyService,
  deleteRateCard,
  deleteRateRule,
  deleteSeason,
  duplicateRateCard,
  duplicateSeason,
  fetchChangeOverRules,
  fetchNearbyPlaceTypes,
  fetchProperties,
  fetchProperty,
  fetchPropertyAvailabilityCells,
  fetchPropertyBookingsForRange,
  fetchPropertyCapacity,
  fetchPropertyCategories,
  fetchPropertyContacts,
  fetchPropertyDescriptions,
  fetchPropertyDiscounts,
  fetchPropertyExtras,
  fetchPropertyFinance,
  fetchPropertyGroups,
  fetchPropertyHolds,
  fetchPropertyImages,
  fetchPropertyLocation,
  fetchPropertyNearbyPlaces,
  fetchPropertyRooms,
  fetchPropertyServices,
  fetchPropertySeasons,
  fetchPropertySettings,
  fetchSeasonDetail,
  reorderPropertyImages,
  reorderPropertyRooms,
  restoreProperty,
  setPropertyImageHero,
  updateChangeOverRule,
  updatePropertyBlock,
  updatePropertyCapacity,
  updatePropertyContact,
  updatePropertyFeatures,
  updatePropertyFinance,
  updatePropertyImage,
  updatePropertyLocation,
  updatePropertyNearbyPlace,
  updatePropertyRoom,
  updatePropertyService,
  updatePropertySettings,
  updateRateCard,
  updateRateRule,
  updateSeason,
  upsertPropertyDescription,
} from "./api";
import type {
  AvailabilityBlockWriteInput,
  ChangeOverRuleWriteInput,
  DescriptionSection,
  PropertyCapacityWriteInput,
  PropertyContactAssignmentWriteInput,
  PropertyCreateInput,
  PropertyFilters,
  PropertyFinanceWriteInput,
  PropertyImageCreateInput,
  PropertyLocationWriteInput,
  PropertyNearbyPlaceWriteInput,
  PropertyRoomWriteInput,
  PropertyServiceWriteInput,
  PropertySettingsWriteInput,
  RateCardWriteInput,
  RatePlanWriteInput,
  RateRuleWritePayload,
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

export function usePropertyCategories() {
  return useQuery({
    queryKey: queryKeys.propertyCategories.list(),
    queryFn: fetchPropertyCategories,
  });
}

export function usePropertyGroups() {
  return useQuery({ queryKey: queryKeys.propertyGroups.list(), queryFn: fetchPropertyGroups });
}

export function useCreateProperty() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyCreateInput) => createProperty(input),
    onSuccess: () => {
      // Invalidate the whole properties tree so every filtered list view picks
      // up the new villa, not just the default filter set.
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.all() });
    },
  });
}

export function usePropertyDescriptions(idOrSlug: PropertyId | undefined) {
  return useQuery(
    enabledQuery(idOrSlug, queryKeys.properties.descriptions, fetchPropertyDescriptions),
  );
}

export function usePropertyRooms(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.rooms, fetchPropertyRooms));
}

export function useCreatePropertyRoom(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyRoomWriteInput) => createPropertyRoom(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.rooms(propertyId) });
    },
  });
}

interface UpdatePropertyRoomVars {
  roomId: number;
  input: Partial<PropertyRoomWriteInput>;
}

export function useUpdatePropertyRoom(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ roomId, input }: UpdatePropertyRoomVars) =>
      updatePropertyRoom(propertyId, roomId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.rooms(propertyId) });
    },
  });
}

export function useDeletePropertyRoom(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ roomId }: { roomId: number }) => deletePropertyRoom(propertyId, roomId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.rooms(propertyId) });
    },
  });
}

export function useReorderPropertyRooms(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (roomIds: number[]) => reorderPropertyRooms(propertyId, roomIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.rooms(propertyId) });
    },
  });
}

export function useNearbyPlaceTypes() {
  return useQuery({
    queryKey: queryKeys.nearbyPlaceTypes.list(),
    queryFn: fetchNearbyPlaceTypes,
    staleTime: 1000 * 60 * 60,
  });
}

export function usePropertyNearbyPlaces(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.nearby, fetchPropertyNearbyPlaces));
}

export function useCreatePropertyNearbyPlace(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyNearbyPlaceWriteInput) =>
      createPropertyNearbyPlace(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.nearby(propertyId) });
    },
  });
}

interface UpdatePropertyNearbyPlaceVars {
  poiId: number;
  input: Partial<PropertyNearbyPlaceWriteInput> & { sort_order?: number };
}

export function useUpdatePropertyNearbyPlace(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ poiId, input }: UpdatePropertyNearbyPlaceVars) =>
      updatePropertyNearbyPlace(propertyId, poiId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.nearby(propertyId) });
    },
  });
}

export function useDeletePropertyNearbyPlace(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ poiId }: { poiId: number }) => deletePropertyNearbyPlace(propertyId, poiId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.nearby(propertyId) });
    },
  });
}

export function usePropertyServices(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.services, fetchPropertyServices));
}

export function useCreatePropertyService(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyServiceWriteInput) => createPropertyService(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.services(propertyId) });
    },
  });
}

interface UpdatePropertyServiceVars {
  serviceId: number;
  input: Partial<PropertyServiceWriteInput> & { sort_order?: number };
}

export function useUpdatePropertyService(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    // The detail route is flat, so the service id alone addresses the row; the
    // propertyId is carried only to invalidate the right list cache.
    mutationFn: ({ serviceId, input }: UpdatePropertyServiceVars) =>
      updatePropertyService(serviceId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.services(propertyId) });
    },
  });
}

export function useDeletePropertyService(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ serviceId }: { serviceId: number }) => deletePropertyService(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.services(propertyId) });
    },
  });
}

export function usePropertySeasons(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.seasons, fetchPropertySeasons));
}

export function useSeasonDetail(seasonId: SeasonId | undefined) {
  return useQuery(enabledQuery(seasonId, queryKeys.properties.seasonDetail, fetchSeasonDetail));
}

export function useCreateSeason(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RatePlanWriteInput) => createSeason(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.seasons(propertyId) });
    },
  });
}

interface UpdateSeasonVars {
  seasonId: SeasonId;
  input: Partial<RatePlanWriteInput>;
}

export function useUpdateSeason(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ seasonId, input }: UpdateSeasonVars) => updateSeason(seasonId, input),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.seasons(propertyId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.properties.seasonDetail(vars.seasonId),
      });
    },
  });
}

export function useDeleteSeason(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ seasonId }: { seasonId: SeasonId }) => deleteSeason(seasonId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.seasons(propertyId) });
    },
  });
}

export function useDuplicateSeason(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ seasonId }: { seasonId: SeasonId }) => duplicateSeason(seasonId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.seasons(propertyId) });
    },
  });
}

function useSeasonDetailInvalidation(seasonId: SeasonId) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.properties.seasonDetail(seasonId),
    });
  };
}

export function useCreateRateCard(seasonId: SeasonId) {
  const invalidate = useSeasonDetailInvalidation(seasonId);
  return useMutation({
    mutationFn: (input: RateCardWriteInput) => createRateCard(seasonId, input),
    onSuccess: invalidate,
  });
}

export function useUpdateRateCard(seasonId: SeasonId) {
  const invalidate = useSeasonDetailInvalidation(seasonId);
  return useMutation({
    mutationFn: ({ cardId, input }: { cardId: number; input: Partial<RateCardWriteInput> }) =>
      updateRateCard(cardId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteRateCard(seasonId: SeasonId) {
  const invalidate = useSeasonDetailInvalidation(seasonId);
  return useMutation({
    mutationFn: ({ cardId }: { cardId: number }) => deleteRateCard(cardId),
    onSuccess: invalidate,
  });
}

export function useDuplicateRateCard(seasonId: SeasonId) {
  const invalidate = useSeasonDetailInvalidation(seasonId);
  return useMutation({
    mutationFn: ({ cardId }: { cardId: number }) => duplicateRateCard(cardId),
    onSuccess: invalidate,
  });
}

export function useCreateRateRule(seasonId: SeasonId) {
  const invalidate = useSeasonDetailInvalidation(seasonId);
  return useMutation({
    mutationFn: ({ cardId, input }: { cardId: number; input: RateRuleWritePayload }) =>
      createRateRule(cardId, input),
    onSuccess: invalidate,
  });
}

export function useUpdateRateRule(seasonId: SeasonId) {
  const invalidate = useSeasonDetailInvalidation(seasonId);
  return useMutation({
    mutationFn: ({ ruleId, input }: { ruleId: number; input: Partial<RateRuleWritePayload> }) =>
      updateRateRule(ruleId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteRateRule(seasonId: SeasonId) {
  const invalidate = useSeasonDetailInvalidation(seasonId);
  return useMutation({
    mutationFn: ({ ruleId }: { ruleId: number }) => deleteRateRule(ruleId),
    onSuccess: invalidate,
  });
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

export function usePropertyAvailabilityCalendar(
  propertyId: number | undefined,
  from: string,
  to: string,
) {
  return useQuery({
    queryKey: queryKeys.properties.availabilityCalendar(propertyId!, from, to),
    queryFn: () => fetchPropertyAvailabilityCells(propertyId!, from, to),
    enabled: propertyId != null,
  });
}

function invalidateAvailability(queryClient: QueryClient, propertyId: number) {
  // The calendar cells and the holds list (which prefills the edit dialog)
  // are independent query trees — a block write must refresh both.
  queryClient.invalidateQueries({
    queryKey: queryKeys.properties.availabilityRoot(propertyId),
  });
  queryClient.invalidateQueries({
    queryKey: queryKeys.properties.holdsRoot(propertyId),
  });
  // The multi-villa timeline reads the same holds through its own key —
  // without this, a block write shows up there only after the staleTime.
  queryClient.invalidateQueries({ queryKey: queryKeys.availability.all() });
}

export function useCreatePropertyBlock(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AvailabilityBlockWriteInput) => createPropertyBlock(propertyId, input),
    onSuccess: () => invalidateAvailability(queryClient, propertyId),
  });
}

interface UpdatePropertyBlockVars {
  blockId: number;
  input: Partial<AvailabilityBlockWriteInput>;
}

export function useUpdatePropertyBlock(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ blockId, input }: UpdatePropertyBlockVars) =>
      updatePropertyBlock(blockId, input),
    onSuccess: () => invalidateAvailability(queryClient, propertyId),
  });
}

export function useDeletePropertyBlock(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ blockId }: { blockId: number }) => deletePropertyBlock(blockId),
    onSuccess: () => invalidateAvailability(queryClient, propertyId),
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
    mutationFn: (input: PropertyImageCreateInput) => createPropertyImage(propertyId, input),
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

export function usePropertyLocation(propertyId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.properties.location(propertyId!),
    queryFn: () => fetchPropertyLocation(propertyId!),
    enabled: propertyId != null,
  });
}

export function useUpdatePropertyLocation(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyLocationWriteInput) => updatePropertyLocation(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.location(propertyId) });
    },
  });
}

export function usePropertyCapacity(propertyId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.properties.capacity(propertyId!),
    queryFn: () => fetchPropertyCapacity(propertyId!),
    enabled: propertyId != null,
  });
}

export function useUpdatePropertyCapacity(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PropertyCapacityWriteInput) => updatePropertyCapacity(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.capacity(propertyId) });
      // The list rows carry a derived `capacity` block (read by the quote
      // builder), so refresh every list cache. `detail` doesn't expose
      // capacity, so it's intentionally left alone.
      queryClient.invalidateQueries({ queryKey: [...queryKeys.properties.all(), "list"] });
    },
  });
}

export function useUpsertPropertyDescription(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ section, body }: { section: DescriptionSection; body: string }) =>
      upsertPropertyDescription(propertyId, section, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.descriptions(propertyId) });
    },
  });
}

export function useDeletePropertyDescription(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ section }: { section: DescriptionSection }) =>
      deletePropertyDescription(propertyId, section),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.descriptions(propertyId) });
    },
  });
}

export function useChangeOverRules(propertyId: number | undefined, effectiveOn?: string) {
  return useQuery({
    queryKey: [...queryKeys.properties.changeover(propertyId!), effectiveOn ?? null],
    queryFn: () => fetchChangeOverRules(propertyId!, effectiveOn),
    enabled: propertyId != null,
  });
}

export function useCreateChangeOverRule(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChangeOverRuleWriteInput) => createChangeOverRule(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.changeover(propertyId) });
    },
  });
}

interface UpdateChangeOverRuleVars {
  ruleId: number;
  input: Partial<ChangeOverRuleWriteInput>;
}

export function useUpdateChangeOverRule(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ruleId, input }: UpdateChangeOverRuleVars) =>
      updateChangeOverRule(ruleId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.changeover(propertyId) });
    },
  });
}

export function useDeleteChangeOverRule(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ruleId }: { ruleId: number }) => deleteChangeOverRule(ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.changeover(propertyId) });
    },
  });
}

export function useUpdatePropertyFeatures(propertyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (featureIds: number[]) => updatePropertyFeatures(propertyId, featureIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.detail(propertyId) });
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
