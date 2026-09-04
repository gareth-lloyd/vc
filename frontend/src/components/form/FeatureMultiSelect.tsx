import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/cn";
import { FEATURE_CATALOGUE_PAGE_SIZE } from "@/lib/domain/features/api";
import { useFeatureCategories, useFeatures } from "@/lib/domain/features/hooks";
import type { Feature, FeatureCategory } from "@/lib/domain/features/schemas";

interface FeatureMultiSelectProps {
  id?: string;
  /** Selected feature slugs. */
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
  className?: string;
}

interface FeatureGroup {
  // The raw feature.category id — always unique per group, unlike
  // `category?.id` which collapses to the same "uncategorised" key for every
  // group whose category failed to resolve (e.g. mid-fetch, dangling FK).
  categoryId: number;
  category: FeatureCategory | undefined;
  items: Feature[];
}

/**
 * Multi-select feature/amenity picker (BUG-019), grouped by category, with
 * chip display for the current selection — built from existing shadcn/Radix
 * primitives (Popover + Checkbox + Badge), no new dependency. Shared by the
 * properties list filter and the quote-builder criteria form.
 */
export function FeatureMultiSelect({
  id,
  value,
  onChange,
  disabled,
  className,
}: FeatureMultiSelectProps) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const featuresQuery = useFeatures({ pageSize: FEATURE_CATALOGUE_PAGE_SIZE });
  const categoriesQuery = useFeatureCategories({ pageSize: FEATURE_CATALOGUE_PAGE_SIZE });

  const features = useMemo(() => featuresQuery.data?.results ?? [], [featuresQuery.data]);
  const categories = useMemo(() => categoriesQuery.data?.results ?? [], [categoriesQuery.data]);

  const featureBySlug = useMemo(() => {
    const map = new Map<string, Feature>();
    for (const f of features) map.set(f.slug, f);
    return map;
  }, [features]);

  const groups = useMemo<FeatureGroup[]>(() => {
    const categoryById = new Map(categories.map((c) => [c.id, c] as const));
    const byCategory = new Map<number, Feature[]>();
    for (const feature of features) {
      if (!feature.is_active) continue;
      const items = byCategory.get(feature.category) ?? [];
      items.push(feature);
      byCategory.set(feature.category, items);
    }
    return [...byCategory.entries()]
      .map(([categoryId, items]) => ({
        categoryId,
        category: categoryById.get(categoryId),
        items: [...items].sort(
          (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
        ),
      }))
      .sort((a, b) => (a.category?.sort_order ?? 0) - (b.category?.sort_order ?? 0));
  }, [features, categories]);

  const toggle = (slug: string, checked: boolean) => {
    onChange(checked ? [...value, slug] : value.filter((v) => v !== slug));
  };

  const remove = (slug: string) => onChange(value.filter((v) => v !== slug));

  const summary =
    value.length === 0
      ? t("feature_multi_select.placeholder")
      : t("feature_multi_select.selected_count", { count: value.length });

  return (
    <div className={cn("space-y-2", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled || featuresQuery.isLoading || categoriesQuery.isLoading}
          >
            {summary}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="max-h-80 w-72 overflow-y-auto p-2">
          {groups.length === 0 ? (
            <p className="text-muted-foreground px-1 py-1 text-xs">
              {t("feature_multi_select.empty")}
            </p>
          ) : (
            groups.map(({ categoryId, category, items }) => (
              <div key={categoryId} className="space-y-1 py-1">
                <p className="text-muted-foreground px-1 pb-1 text-xs font-medium">
                  {category?.name ?? t("feature_multi_select.uncategorised")}
                </p>
                {items.map((feature) => (
                  <CheckboxLabel key={feature.slug}>
                    <Checkbox
                      checked={value.includes(feature.slug)}
                      onCheckedChange={(v) => toggle(feature.slug, v === true)}
                    />
                    <span>{feature.name}</span>
                  </CheckboxLabel>
                ))}
              </div>
            ))
          )}
        </PopoverContent>
      </Popover>
      {value.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {value.map((slug) => {
            const label = featureBySlug.get(slug)?.name ?? slug;
            return (
              <Badge key={slug} variant="outline" className="gap-1">
                {label}
                {disabled ? null : (
                  <button
                    type="button"
                    onClick={() => remove(slug)}
                    aria-label={t("feature_multi_select.remove_label", { name: label })}
                    className="hover:text-destructive"
                  >
                    ✕
                  </button>
                )}
              </Badge>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
