import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { FeatureIcon } from "@/components/data/FeatureIcon";
import { useFeatureCategories, useFeatures } from "@/features/admin/tags/hooks";
import type { Feature, FeatureCategory } from "@/features/admin/tags/schemas";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { ApiError } from "@/lib/api/errors";
import { useUpdatePropertyFeatures } from "../hooks";
import type { PropertyDetail } from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface FeaturesContext {
  property: PropertyDetail;
}

interface CategorySectionProps {
  category: FeatureCategory;
  features: Feature[];
  selected: Set<number>;
  canWrite: boolean;
  onToggle: (id: number) => void;
}

function CategorySection({
  category,
  features,
  selected,
  canWrite,
  onToggle,
}: CategorySectionProps) {
  const sorted = useMemo(
    () => [...features].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name)),
    [features],
  );
  return (
    <section className="space-y-3">
      <h3 className="text-foreground flex items-center gap-2 text-sm font-semibold">
        <FeatureIcon name={category.icon} className="text-muted-foreground size-4" />
        {category.name}
      </h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((feature) => {
          const id = `feature-${feature.id}`;
          const isChecked = selected.has(feature.id);
          return (
            <div
              key={feature.id}
              className="border-border bg-card flex items-start gap-2 rounded-md border p-2"
            >
              <Checkbox
                id={id}
                checked={isChecked}
                disabled={!canWrite}
                onCheckedChange={() => onToggle(feature.id)}
              />
              <Label htmlFor={id} className="flex items-center gap-1.5 text-sm font-normal">
                <FeatureIcon
                  name={feature.icon}
                  className="text-muted-foreground size-4 shrink-0"
                />
                {feature.name}
              </Label>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function FeaturesTab() {
  const { property } = useOutletContext<FeaturesContext>();
  const { t } = useTranslation("properties");
  const canWrite = useHasReservationsRole();
  const features = useFeatures({});
  const categories = useFeatureCategories({});
  const saveMutation = useUpdatePropertyFeatures(property.id);

  const initialSelected = useMemo(
    () => new Set<number>(property.feature_ids ?? []),
    [property.feature_ids],
  );
  const [selected, setSelected] = useState<Set<number>>(initialSelected);
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  // Reset only when navigating between properties — refetches of the same
  // property must not clobber in-flight user edits (e.g. after Save).
  useEffect(() => {
    setSelected(new Set<number>(property.feature_ids ?? []));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [property.id]);

  const isDirty = useMemo(() => {
    if (selected.size !== initialSelected.size) return true;
    for (const id of selected) {
      if (!initialSelected.has(id)) return true;
    }
    return false;
  }, [selected, initialSelected]);

  const featuresByCategory = useMemo(() => {
    const map = new Map<number, Feature[]>();
    for (const f of features.data?.results ?? []) {
      if (!f.is_active) continue;
      const list = map.get(f.category) ?? [];
      list.push(f);
      map.set(f.category, list);
    }
    return map;
  }, [features.data?.results]);

  const orderedCategories = useMemo(() => {
    const rows = categories.data?.results ?? [];
    return [...rows]
      .filter((c) => c.is_active)
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
  }, [categories.data?.results]);

  const handleToggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSave = async () => {
    setTopLevelError(null);
    try {
      await saveMutation.mutateAsync(Array.from(selected));
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
    setSelected(initialSelected);
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
          <Button variant="outline" size="sm" onClick={handleReset} disabled={!isDirty}>
            {t("features.actions.reset")}
          </Button>
          {saveButton}
        </div>
      </div>

      {orderedCategories.length === 0 ? (
        <EmptyState
          title={t("features.empty.title")}
          description={t("features.empty.description")}
        />
      ) : (
        <div className="space-y-6">
          {orderedCategories.map((category) => {
            const list = featuresByCategory.get(category.id) ?? [];
            if (list.length === 0) return null;
            return (
              <CategorySection
                key={category.id}
                category={category}
                features={list}
                selected={selected}
                canWrite={canWrite}
                onToggle={handleToggle}
              />
            );
          })}
        </div>
      )}

      <FormErrorAlert message={topLevelError} />
    </div>
  );
}
