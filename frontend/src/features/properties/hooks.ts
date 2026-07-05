import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { queryKeys, type PropertyId, type RatePlanId } from "@/lib/query/keys";
import { enabledQuery } from "@/lib/query/enabledQuery";
import {
  activateProperty,
  archiveProperty,
  confirmPropertyAvailability,
  createChangeOverRule,
  createProperty,
  createPropertyBlock,
  createPropertyContact,
  createPropertyImage,
  createPropertyNearbyPlace,
  createPropertyRoom,
  createPropertyService,
  createRatePeriod,
  createRateBand,
  createRatePlan,
  deleteChangeOverRule,
  deletePropertyBlock,
  deletePropertyContact,
  deletePropertyDescription,
  deletePropertyImage,
  deletePropertyNearbyPlace,
  deletePropertyRoom,
  deletePropertyService,
  deleteRatePeriod,
  deleteRateBand,
  deleteRatePlan,
  duplicateRatePlan,
  fetchChangeOverRules,
  fetchCollections,
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
  fetchPropertyRatePlans,
  fetchPropertySettings,
  fetchRatePlanDetail,
  fetchRegions,
  type RegionListFilters,
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
  updateRatePeriod,
  updateRateBand,
  updateRatePlan,
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
  RatePeriodWriteInput,
  RatePlanWriteInput,
  RateBandWritePayload,
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

export function useRegions(filters?: RegionListFilters) {
  return useQuery({
    queryKey: queryKeys.regions.list(filters),
    queryFn: () => fetchRegions(filters),
  });
}

export function useCollections() {
  return useQuery({ queryKey: queryKeys.collections.list(), queryFn: fetchCollections });
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

export function usePropertyRatePlans(idOrSlug: PropertyId | undefined) {
  return useQuery(enabledQuery(idOrSlug, queryKeys.properties.ratePlans, fetchPropertyRatePlans));
}

export function useRatePlanDetail(ratePlanId: RatePlanId | undefined) {
  return useQuery(
    enabledQuery(ratePlanId, queryKeys.properties.ratePlanDetail, fetchRatePlanDetail),
  );
}

export function useCreateRatePlan(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RatePlanWriteInput) => createRatePlan(propertyId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.ratePlans(propertyId) });
    },
  });
}

interface UpdateSeasonVars {
  ratePlanId: RatePlanId;
  input: Partial<RatePlanWriteInput>;
}

export function useUpdateRatePlan(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ratePlanId, input }: UpdateSeasonVars) => updateRatePlan(ratePlanId, input),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.ratePlans(propertyId) });
      queryClient.invalidateQueries({
        queryKey: queryKeys.properties.ratePlanDetail(vars.ratePlanId),
      });
    },
  });
}

export function useDeleteRatePlan(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ratePlanId }: { ratePlanId: RatePlanId }) => deleteRatePlan(ratePlanId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.ratePlans(propertyId) });
    },
  });
}

export function useDuplicateRatePlan(propertyId: PropertyId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ratePlanId }: { ratePlanId: RatePlanId }) => duplicateRatePlan(ratePlanId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.properties.ratePlans(propertyId) });
    },
  });
}

function useRatePlanDetailInvalidation(ratePlanId: RatePlanId) {
  const queryClient = useQueryClient();
  return () => {
    // `refetchType: "all"` so the rate-plan detail refetches even when the
    // workbench reads it through a `useQueries` fan-out entry that React Query
    // treats as momentarily inactive — otherwise a just-added period/band stays
    // invisible until a manual page reload.
    void queryClient.invalidateQueries({
      queryKey: queryKeys.properties.ratePlanDetail(ratePlanId),
      refetchType: "all",
    });
  };
}

export function useCreateRatePeriod(ratePlanId: RatePlanId) {
  const invalidate = useRatePlanDetailInvalidation(ratePlanId);
  return useMutation({
    mutationFn: (input: RatePeriodWriteInput) => createRatePeriod(ratePlanId, input),
    onSuccess: invalidate,
  });
}

export function useUpdateRatePeriod(ratePlanId: RatePlanId) {
  const invalidate = useRatePlanDetailInvalidation(ratePlanId);
  return useMutation({
    mutationFn: ({ periodId, input }: { periodId: number; input: Partial<RatePeriodWriteInput> }) =>
      updateRatePeriod(periodId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteRatePeriod(ratePlanId: RatePlanId) {
  const invalidate = useRatePlanDetailInvalidation(ratePlanId);
  return useMutation({
    mutationFn: ({ periodId }: { periodId: number }) => deleteRatePeriod(periodId),
    onSuccess: invalidate,
  });
}

export function useCreateRateBand(ratePlanId: RatePlanId) {
  const invalidate = useRatePlanDetailInvalidation(ratePlanId);
  return useMutation({
    mutationFn: ({ periodId, input }: { periodId: number; input: RateBandWritePayload }) =>
      createRateBand(periodId, input),
    onSuccess: invalidate,
  });
}

export function useUpdateRateBand(ratePlanId: RatePlanId) {
  const invalidate = useRatePlanDetailInvalidation(ratePlanId);
  return useMutation({
    mutationFn: ({ bandId, input }: { bandId: number; input: Partial<RateBandWritePayload> }) =>
      updateRateBand(bandId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteRateBand(ratePlanId: RatePlanId) {
  const invalidate = useRatePlanDetailInvalidation(ratePlanId);
  return useMutation({
    mutationFn: ({ bandId }: { bandId: number }) => deleteRateBand(bandId),
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

// GAP-033: staff "Mark as up-to-date". Refresh the property detail (the
// AvailabilityTab reads its freshness badges off the detail via useOutletContext)
// AND the availability/timeline caches (Unit 7 surfaces the same badges there).
export function useConfirmPropertyAvailability(property: { id: number; slug?: string | null }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => confirmPropertyAvailability(property.id),
    onSuccess: () => {
      invalidatePropertyDetail(queryClient, property);
      invalidateAvailability(queryClient, property.id);
    },
  });
}
