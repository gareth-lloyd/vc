import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { toast } from "sonner";
import { DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Badge } from "@/components/ui/badge";
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
import { useFeatureCategories, useFeatures } from "@/features/admin/tags/hooks";
import type { Feature } from "@/features/admin/tags/schemas";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api/errors";
import { useUpdatePropertyFeatures } from "../hooks";
import type { PropertyDetail } from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface FeaturesContext {
  property: PropertyDetail;
}

interface SelectedFeatureRowProps {
  id: number;
  feature: Feature | undefined;
  categoryName: string | undefined;
  canWrite: boolean;
  onRemove: (id: number) => void;
  t: TFunction<"properties">;
}

function SelectedFeatureRow({
  id,
  feature,
  categoryName,
  canWrite,
  onRemove,
  t,
}: SelectedFeatureRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
    disabled: !canWrite,
  });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const name = feature?.name ?? t("features.row.unknown_feature");

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={cn(
        "border-border bg-card flex items-center justify-between gap-3 rounded-md border p-2",
        isDragging && "opacity-60",
      )}
      data-testid={`property-feature-row-${id}`}
    >
      <div
        className="flex min-w-0 flex-1 items-center gap-2"
        {...(canWrite ? { ...attributes, ...listeners } : {})}
        aria-label={canWrite ? t("features.row.drag_handle_label") : undefined}
        role={canWrite ? "button" : undefined}
      >
        <span className="text-muted-foreground px-1 select-none">⋮⋮</span>
        <FeatureIcon name={feature?.icon ?? ""} className="text-muted-foreground size-4 shrink-0" />
        <span className="truncate text-sm font-medium">{name}</span>
        {categoryName ? <Badge variant="outline">{categoryName}</Badge> : null}
      </div>
      {canWrite ? (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2"
          aria-label={t("features.row.remove_label", { name })}
          onClick={() => onRemove(id)}
        >
          ✕
        </Button>
      ) : null}
    </li>
  );
}

export function FeaturesTab() {
  const { property } = useOutletContext<FeaturesContext>();
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const features = useFeatures({});
  const categories = useFeatureCategories({});
  const saveMutation = useUpdatePropertyFeatures(property.id);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  // The ORDERED list of selected feature ids is the source of truth — its index
  // becomes each link's `sort_order` server-side (GAP-022). Reordering is a real
  // edit, so `isDirty` is order-sensitive (unlike the old Set-based grid).
  const initialOrder = useMemo(() => property.feature_ids ?? [], [property.feature_ids]);
  const [order, setOrder] = useState<number[]>(initialOrder);
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  // Reset only when navigating between properties — refetches of the same
  // property (e.g. after Save invalidates the detail query) must not clobber
  // in-flight edits. After Save the server echoes the persisted order, so
  // `initialOrder` catches up and `isDirty` settles to false on its own.
  useEffect(() => {
    setOrder(property.feature_ids ?? []);
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

  const selectedSet = useMemo(() => new Set(order), [order]);

  const isDirty = useMemo(() => {
    if (order.length !== initialOrder.length) return true;
    return order.some((id, i) => id !== initialOrder[i]);
  }, [order, initialOrder]);

  // Unselected, active features offered by the add control, sorted by category
  // then per-category rank — grouping the dropdown without a grouped data shape.
  const availableToAdd = useMemo(() => {
    const catSort = new Map(
      (categories.data?.results ?? []).map((c) => [c.id, c.sort_order] as const),
    );
    return (features.data?.results ?? [])
      .filter((f) => f.is_active && !selectedSet.has(f.id))
      .sort(
        (a, b) =>
          (catSort.get(a.category) ?? 0) - (catSort.get(b.category) ?? 0) ||
          a.sort_order - b.sort_order ||
          a.name.localeCompare(b.name),
      );
  }, [features.data?.results, categories.data?.results, selectedSet]);

  const hasCatalogue = useMemo(
    () => (features.data?.results ?? []).some((f) => f.is_active),
    [features.data?.results],
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setOrder((prev) => {
      const oldIndex = prev.indexOf(Number(active.id));
      const newIndex = prev.indexOf(Number(over.id));
      if (oldIndex < 0 || newIndex < 0) return prev;
      return arrayMove(prev, oldIndex, newIndex);
    });
  };

  const handleAdd = (id: number) => {
    setOrder((prev) => (prev.includes(id) ? prev : [...prev, id]));
  };

  const handleRemove = (id: number) => {
    setOrder((prev) => prev.filter((x) => x !== id));
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
      ) : order.length === 0 ? (
        <EmptyState
          title={t("features.none_selected.title")}
          description={t("features.none_selected.description")}
        />
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <SortableContext items={order} strategy={verticalListSortingStrategy}>
            <ul className="space-y-2">
              {order.map((id) => {
                const feature = featuresById.get(id);
                return (
                  <SelectedFeatureRow
                    key={id}
                    id={id}
                    feature={feature}
                    categoryName={feature ? categoryNameById.get(feature.category) : undefined}
                    canWrite={canWrite}
                    onRemove={handleRemove}
                    t={t}
                  />
                );
              })}
            </ul>
          </SortableContext>
        </DndContext>
      )}

      <FormErrorAlert message={topLevelError} />
    </div>
  );
}
