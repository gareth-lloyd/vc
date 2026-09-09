import { useEffect, useMemo, useRef, useState } from "react";
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
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { FeatureIcon } from "@/components/data/FeatureIcon";
import type { Feature } from "@/lib/domain/features/schemas";
import { ApiError } from "@/lib/api/errors";
import {
  useDeletePropertyDescription,
  usePropertyDescriptions,
  useUpsertPropertyDescription,
} from "../hooks";
import { OTHER_INFORMATION_SECTION } from "../schemas";
import { DerivedFeatureChip } from "./DerivedFeatureChip";
import { SelectedFeatureRow } from "./SelectedFeatureRow";

interface OtherInformationSectionProps {
  propertyId: number;
  canWrite: boolean;
  /** Selected tag ids in list order — a filtered view of FeaturesTab's `order`. */
  tagOrder: number[];
  featuresById: Map<number, Feature>;
  /** Unselected, active tags offered by the Add menu. */
  availableTags: Feature[];
  /** Read-only tags derived from room attributes (GAP-067), in API order. */
  derivedTags: { id: number; feature: Feature | undefined }[];
  /** False when the catalogue has no active `other-information` feature. */
  hasVocabulary: boolean;
  onAdd: (id: number) => void;
  onRemove: (id: number) => void;
  onReorder: (nextTagOrder: number[]) => void;
}

/**
 * "Other information" on the Features tab (GAP-091): the property's
 * other-information tags (an ordered view over the tab's `order`, saved by the
 * tab's Save button) plus the free-text `other_information` description, which
 * saves through its own Save/Clear via the descriptions endpoint.
 */
export function OtherInformationSection({
  propertyId,
  canWrite,
  tagOrder,
  featuresById,
  availableTags,
  derivedTags,
  hasVocabulary,
  onAdd,
  onRemove,
  onReorder,
}: OtherInformationSectionProps) {
  const { t } = useTranslation("properties");
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = tagOrder.indexOf(Number(active.id));
    const newIndex = tagOrder.indexOf(Number(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    onReorder(arrayMove(tagOrder, oldIndex, newIndex));
  };

  const addControl =
    canWrite && hasVocabulary ? (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" disabled={availableTags.length === 0}>
            {t("features.otherInformation.actions.add")}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
          {availableTags.map((feature) => (
            <DropdownMenuItem key={feature.id} className="gap-2" onClick={() => onAdd(feature.id)}>
              <FeatureIcon name={feature.icon} className="text-muted-foreground size-4 shrink-0" />
              <span className="flex-1">{feature.name}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    ) : null;

  return (
    <section
      data-testid="other-information-section"
      className="border-border space-y-4 border-t pt-6"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">{t("features.otherInformation.title")}</h3>
          <p className="text-muted-foreground text-sm">{t("features.otherInformation.hint")}</p>
        </div>
        {addControl}
      </div>

      {!hasVocabulary ? (
        <EmptyState
          title={t("features.otherInformation.empty.title")}
          description={t("features.otherInformation.empty.description")}
          className="py-6"
        />
      ) : tagOrder.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          {t("features.otherInformation.none_selected")}
        </p>
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <SortableContext items={tagOrder} strategy={verticalListSortingStrategy}>
            <ul className="space-y-2">
              {tagOrder.map((id) => (
                <SelectedFeatureRow
                  key={id}
                  id={id}
                  feature={featuresById.get(id)}
                  canWrite={canWrite}
                  onRemove={onRemove}
                  dragHandleLabel={t("features.otherInformation.row.drag_handle_label")}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      )}

      {derivedTags.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {derivedTags.map(({ id, feature }) => (
            <DerivedFeatureChip key={id} id={id} feature={feature} />
          ))}
        </ul>
      ) : null}

      {/* Keyed so a draft for one villa is dropped, not carried to the next. */}
      <OtherInformationDescription key={propertyId} propertyId={propertyId} canWrite={canWrite} />
    </section>
  );
}

interface OtherInformationDescriptionProps {
  propertyId: number;
  canWrite: boolean;
}

function OtherInformationDescription({ propertyId, canWrite }: OtherInformationDescriptionProps) {
  const { t } = useTranslation("properties");
  const descriptions = usePropertyDescriptions(propertyId);
  const upsertMutation = useUpsertPropertyDescription(propertyId);
  const deleteMutation = useDeletePropertyDescription(propertyId);

  const initialBody = useMemo(
    () =>
      descriptions.data?.results.find((r) => r.section === OTHER_INFORMATION_SECTION)?.body ?? "",
    [descriptions.data?.results],
  );
  const [body, setBody] = useState(initialBody);
  const [clearing, setClearing] = useState(false);

  // Seed from the first successful fetch only — the refetch after Save must
  // not clobber an edit in progress (same guard as DescriptionsSection).
  const seeded = useRef(false);
  useEffect(() => {
    if (!seeded.current && descriptions.data) {
      setBody(initialBody);
      seeded.current = true;
    }
  }, [descriptions.data, initialBody]);

  const handleSave = async () => {
    try {
      await upsertMutation.mutateAsync({ section: OTHER_INFORMATION_SECTION, body });
      toast.success(t("features.otherInformation.description.toasts.saved"));
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.detail);
      } else {
        toast.error(t("features.otherInformation.description.toasts.save_failed"));
      }
    }
  };

  const handleClear = async () => {
    try {
      await deleteMutation.mutateAsync({ section: OTHER_INFORMATION_SECTION });
      // The `seeded` guard blocks the refetch from reseeding, so drop the
      // local copy explicitly or the cleared text stays on screen.
      setBody("");
      toast.success(t("features.otherInformation.description.toasts.cleared"));
      setClearing(false);
    } catch {
      toast.error(t("features.otherInformation.description.toasts.clear_failed"));
    }
  };

  if (descriptions.isLoading) {
    return <Skeleton className="h-24 w-full" />;
  }

  if (descriptions.isError) {
    return (
      <ErrorState
        description={t("features.otherInformation.description.errors.load_failed")}
        onRetry={() => descriptions.refetch()}
        retrying={descriptions.isFetching}
      />
    );
  }

  const textareaId = `description-${OTHER_INFORMATION_SECTION}`;
  const saving = upsertMutation.isPending;

  return (
    <div className="space-y-3">
      <Label htmlFor={textareaId}>{t("features.otherInformation.description.label")}</Label>
      <Textarea
        id={textareaId}
        rows={6}
        value={body}
        disabled={!canWrite}
        onChange={(e) => setBody(e.target.value)}
        placeholder={t("features.otherInformation.description.placeholder")}
      />
      <div className="flex items-center justify-end gap-2">
        {canWrite ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setClearing(true)}
            disabled={!initialBody || body !== initialBody}
          >
            {t("features.otherInformation.description.actions.clear")}
          </Button>
        ) : null}
        {canWrite ? (
          <Button size="sm" onClick={handleSave} disabled={body === initialBody || saving}>
            {saving
              ? t("features.otherInformation.description.actions.saving")
              : t("features.otherInformation.description.actions.save")}
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" disabled>
                  {t("features.otherInformation.description.actions.save")}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{t("descriptions.save_disabled_tooltip")}</TooltipContent>
          </Tooltip>
        )}
      </div>

      {clearing ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setClearing(false)}
          onConfirm={handleClear}
          title={t("features.otherInformation.description.clear_confirm.title")}
          description={t("features.otherInformation.description.clear_confirm.description")}
          confirmLabel={t("features.otherInformation.description.clear_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
