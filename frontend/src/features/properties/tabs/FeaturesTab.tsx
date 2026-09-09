import { useCallback, useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { FeatureIcon } from "@/components/data/FeatureIcon";
import { FEATURE_CATALOGUE_PAGE_SIZE } from "@/lib/domain/features/api";
import { useFeatureCategories, useFeatures } from "@/lib/domain/features/hooks";
import { OTHER_INFORMATION_CATEGORY_SLUG, type Feature } from "@/lib/domain/features/schemas";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { ApiError } from "@/lib/api/errors";
import { usePropertyDescriptions, useUpdatePropertyFeatures } from "../hooks";
import type { PropertyDetail } from "../schemas";
import { OtherInformationSection } from "../components/OtherInformationSection";
import { DerivedFeatureChip } from "../components/DerivedFeatureChip";
import { SelectedFeatureRow } from "../components/SelectedFeatureRow";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface FeaturesContext {
  property: PropertyDetail;
}

export function FeaturesTab() {
  const { property } = useOutletContext<FeaturesContext>();
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const features = useFeatures({ pageSize: FEATURE_CATALOGUE_PAGE_SIZE });
  const categories = useFeatureCategories({ pageSize: FEATURE_CATALOGUE_PAGE_SIZE });
  const saveMutation = useUpdatePropertyFeatures(property.id);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  // Features auto-derived from room attributes (GAP-067) are read-only here:
  // the recompute owns them, so the editor renders them as chips and keeps them
  // out of the manual (draggable) list AND the save payload. `feature_ids` is
  // the full set; subtract the derived subset to get the manual list.
  const derivedSet = useMemo(
    () => new Set(property.derived_feature_ids ?? []),
    [property.derived_feature_ids],
  );
  const manualFeatureIds = (p: PropertyDetail, derived: Set<number>) =>
    (p.feature_ids ?? []).filter((id) => !derived.has(id));

  // The ORDERED list of MANUAL feature ids is the source of truth — its index
  // becomes each link's `sort_order` server-side (GAP-022). Reordering is a real
  // edit, so `isDirty` is order-sensitive (unlike the old Set-based grid).
  const initialOrder = useMemo(
    () => manualFeatureIds(property, derivedSet),
    [property, derivedSet],
  );
  const [order, setOrder] = useState<number[]>(initialOrder);
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  // Start the descriptions fetch now rather than after the catalogue gate
  // below; the Other-information section's own hook dedupes onto this key.
  usePropertyDescriptions(property.id);

  // Reset only when navigating between properties — refetches of the same
  // property (e.g. after Save invalidates the detail query) must not clobber
  // in-flight edits. After Save the server echoes the persisted order, so
  // `initialOrder` catches up and `isDirty` settles to false on its own.
  useEffect(() => {
    setOrder(manualFeatureIds(property, derivedSet));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [property.id]);

  const featuresById = useMemo(() => {
    const map = new Map<number, Feature>();
    for (const f of features.data?.results ?? []) map.set(f.id, f);
    return map;
  }, [features.data?.results]);

  const categoryNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const c of categories.data?.results ?? []) map.set(c.id, c.name);
    return map;
  }, [categories.data?.results]);

  // GAP-091: "other information" tags are the features in the
  // `other-information` category. They render in their own section below the
  // main list but share `order` — the Save payload is still one ordered list.
  const otherInformationCategoryId = useMemo(
    () =>
      (categories.data?.results ?? []).find((c) => c.slug === OTHER_INFORMATION_CATEGORY_SLUG)?.id,
    [categories.data?.results],
  );
  const isTag = useCallback(
    (id: number) =>
      otherInformationCategoryId !== undefined &&
      featuresById.get(id)?.category === otherInformationCategoryId,
    [otherInformationCategoryId, featuresById],
  );

  // Filtered VIEWS of `order`, which is never re-canonicalised: a loaded
  // property can have tag and main ids interleaved (legacy MappingOrder is
  // per-category) and nothing downstream needs them partitioned — the Zoho
  // block and both lists order within their own kind. So add appends, remove
  // filters, and a drag permutes ids within the slots its kind already holds;
  // only genuinely moved links change sort_order (audit rows per link).
  const mainOrder = useMemo(() => order.filter((id) => !isTag(id)), [order, isTag]);
  const tagOrder = useMemo(() => order.filter(isTag), [order, isTag]);
  const placeView = (ofKind: (id: number) => boolean, nextView: number[]) => {
    let i = 0;
    return order.map((id) => (ofKind(id) ? nextView[i++]! : id));
  };

  const selectedSet = useMemo(() => new Set(order), [order]);

  const isDirty = useMemo(() => {
    if (order.length !== initialOrder.length) return true;
    return order.some((id, i) => id !== initialOrder[i]);
  }, [order, initialOrder]);

  // Unselected, active features offered by the add controls, sorted by category
  // then per-category rank — grouping the dropdown without a grouped data shape.
  const availableFeatures = useMemo(() => {
    const catSort = new Map(
      (categories.data?.results ?? []).map((c) => [c.id, c.sort_order] as const),
    );
    return (features.data?.results ?? [])
      .filter((f) => f.is_active && !selectedSet.has(f.id) && !derivedSet.has(f.id))
      .sort(
        (a, b) =>
          (catSort.get(a.category) ?? 0) - (catSort.get(b.category) ?? 0) ||
          a.sort_order - b.sort_order ||
          a.name.localeCompare(b.name),
      );
  }, [features.data?.results, categories.data?.results, selectedSet, derivedSet]);
  const availableToAdd = availableFeatures.filter((f) => !isTag(f.id));
  const availableTags = availableFeatures.filter((f) => isTag(f.id));

  // Read-only derived features, preserving the API's order; tags go to the
  // other-information section's chips, the rest to the main "From rooms" block.
  const derivedFeatures = useMemo(
    () => (property.derived_feature_ids ?? []).map((id) => ({ id, feature: featuresById.get(id) })),
    [property.derived_feature_ids, featuresById],
  );
  const derivedMain = derivedFeatures.filter(({ id }) => !isTag(id));
  const derivedTags = derivedFeatures.filter(({ id }) => isTag(id));

  const hasCatalogue = (features.data?.results ?? []).some((f) => f.is_active && !isTag(f.id));
  // Presence, not activity: a selected tag whose feature was deactivated must
  // stay visible and removable, so the empty state only means "no tag rows".
  const hasTagVocabulary = (features.data?.results ?? []).some((f) => isTag(f.id));

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = mainOrder.indexOf(Number(active.id));
    const newIndex = mainOrder.indexOf(Number(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    setOrder(placeView((id) => !isTag(id), arrayMove(mainOrder, oldIndex, newIndex)));
  };

  const handleAdd = (id: number) => {
    setOrder((prev) => (prev.includes(id) ? prev : [...prev, id]));
  };

  const handleRemove = (id: number) => {
    setOrder((prev) => prev.filter((x) => x !== id));
  };

  const handleReorderTags = (nextTagOrder: number[]) => {
    setOrder(placeView(isTag, nextTagOrder));
  };

  const handleSave = async () => {
    setTopLevelError(null);
    try {
      // Send `order` verbatim — list position is the persisted sort_order.
      await saveMutation.mutateAsync(order);
      toast.success(t("features.toasts.saved"));
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail);
      } else {
        toast.error(t("features.toasts.save_failed"));
      }
    }
  };

  const handleReset = () => {
    setOrder(initialOrder);
    setTopLevelError(null);
  };

  if (features.isLoading || categories.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (features.isError || categories.isError) {
    return (
      <div className="p-6">
        <ErrorState
          description={t("features.errors.load_failed")}
          onRetry={() => {
            features.refetch();
            categories.refetch();
          }}
          retrying={features.isFetching || categories.isFetching}
        />
      </div>
    );
  }

  const addControl = canWrite ? (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={availableToAdd.length === 0}>
          {t("features.actions.add")}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
        {availableToAdd.map((feature) => (
          <DropdownMenuItem
            key={feature.id}
            className="gap-2"
            onClick={() => handleAdd(feature.id)}
          >
            <FeatureIcon name={feature.icon} className="text-muted-foreground size-4 shrink-0" />
            <span className="flex-1">{feature.name}</span>
            <span className="text-muted-foreground text-xs">
              {categoryNameById.get(feature.category)}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  ) : null;

  const saveButton = canWrite ? (
    <Button size="sm" onClick={handleSave} disabled={!isDirty || saveMutation.isPending}>
      {saveMutation.isPending ? t("features.actions.saving") : t("features.actions.save")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("features.actions.save")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("features.save_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("features.title")}</h2>
        <div className="flex items-center gap-2">
          {addControl}
          <Button variant="outline" size="sm" onClick={handleReset} disabled={!isDirty}>
            {t("features.actions.reset")}
          </Button>
          {saveButton}
        </div>
      </div>

      {!hasCatalogue ? (
        <EmptyState
          title={t("features.empty.title")}
          description={t("features.empty.description")}
        />
      ) : mainOrder.length === 0 ? (
        <EmptyState
          title={t("features.none_selected.title")}
          description={t("features.none_selected.description")}
        />
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <SortableContext items={mainOrder} strategy={verticalListSortingStrategy}>
            <ul className="space-y-2">
              {mainOrder.map((id) => {
                const feature = featuresById.get(id);
                return (
                  <SelectedFeatureRow
                    key={id}
                    id={id}
                    feature={feature}
                    categoryName={feature ? categoryNameById.get(feature.category) : undefined}
                    canWrite={canWrite}
                    onRemove={handleRemove}
                  />
                );
              })}
            </ul>
          </SortableContext>
        </DndContext>
      )}

      {derivedMain.length > 0 ? (
        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-muted-foreground text-sm font-medium">
              {t("features.derived.title")}
            </h3>
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className="text-muted-foreground cursor-help text-xs select-none"
                  aria-label={t("features.derived.tooltip")}
                >
                  ⓘ
                </span>
              </TooltipTrigger>
              <TooltipContent>{t("features.derived.tooltip")}</TooltipContent>
            </Tooltip>
          </div>
          <ul className="flex flex-wrap gap-2">
            {derivedMain.map(({ id, feature }) => (
              <DerivedFeatureChip key={id} id={id} feature={feature} />
            ))}
          </ul>
        </section>
      ) : null}

      <FormErrorAlert message={topLevelError} />

      <OtherInformationSection
        propertyId={property.id}
        canWrite={canWrite}
        tagOrder={tagOrder}
        featuresById={featuresById}
        availableTags={availableTags}
        derivedTags={derivedTags}
        hasVocabulary={hasTagVocabulary}
        onAdd={handleAdd}
        onRemove={handleRemove}
        onReorder={handleReorderTags}
      />
    </div>
  );
}
