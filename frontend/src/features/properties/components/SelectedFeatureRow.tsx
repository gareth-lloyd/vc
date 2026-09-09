import { useTranslation } from "react-i18next";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FeatureIcon } from "@/components/data/FeatureIcon";
import type { Feature } from "@/lib/domain/features/schemas";
import { cn } from "@/lib/cn";

interface SelectedFeatureRowProps {
  id: number;
  feature: Feature | undefined;
  categoryName?: string;
  canWrite: boolean;
  onRemove: (id: number) => void;
  /** Overrides the default "Drag to reorder feature" handle label. */
  dragHandleLabel?: string;
}

/**
 * One sortable row of a property's selected features. Shared by the main
 * feature list and the "Other information" tag list on the Features tab —
 * both are ordered views over the same `order` state (GAP-091).
 */
export function SelectedFeatureRow({
  id,
  feature,
  categoryName,
  canWrite,
  onRemove,
  dragHandleLabel,
}: SelectedFeatureRowProps) {
  const { t } = useTranslation("properties");
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
        aria-label={canWrite ? (dragHandleLabel ?? t("features.row.drag_handle_label")) : undefined}
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
