import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { FeatureIcon } from "@/components/data/FeatureIcon";
import type { Feature } from "@/lib/domain/features/schemas";

interface DerivedFeatureChipProps {
  id: number;
  feature: Feature | undefined;
}

/** Read-only chip for a feature derived from room attributes (GAP-067). */
export function DerivedFeatureChip({ id, feature }: DerivedFeatureChipProps) {
  const { t } = useTranslation("properties");
  return (
    <li
      data-testid={`property-derived-feature-${id}`}
      className="border-border bg-muted/40 flex items-center gap-2 rounded-md border px-2 py-1"
    >
      <FeatureIcon name={feature?.icon ?? ""} className="text-muted-foreground size-4 shrink-0" />
      <span className="truncate text-sm">{feature?.name ?? t("features.row.unknown_feature")}</span>
      <Badge variant="outline">{t("features.derived.badge")}</Badge>
    </li>
  );
}
