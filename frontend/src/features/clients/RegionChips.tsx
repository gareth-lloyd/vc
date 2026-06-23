import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { useRegions } from "@/features/availability/hooks";

/**
 * Renders a client's region slugs as chips, labelled by region name.
 *
 * The list endpoint returns region *slugs* (the app-wide region key, same as the
 * region `<Select>` filters); names come from `useRegions()` so labels stay
 * i18n/locale-consistent and the payload stays light. An unknown slug falls back
 * to the raw slug rather than vanishing.
 */
export function RegionChips({ slugs }: { slugs: string[] }) {
  const { data } = useRegions();
  const nameBySlug = useMemo(() => {
    const map = new Map<string, string>();
    data?.results.forEach((region) => map.set(region.slug, region.name));
    return map;
  }, [data]);

  if (slugs.length === 0) return <span className="text-muted-foreground">—</span>;

  const chips = slugs
    .map((slug) => ({ slug, label: nameBySlug.get(slug) ?? slug }))
    .sort((a, b) => a.label.localeCompare(b.label));

  return (
    <div className="flex flex-wrap gap-1">
      {chips.map((chip) => (
        <Badge key={chip.slug} variant="outline">
          {chip.label}
        </Badge>
      ))}
    </div>
  );
}
