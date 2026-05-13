import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSortingStrategy, useSortable } from "@dnd-kit/sortable";
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
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/cn";
import {
  useDeletePropertyImage,
  usePropertyImages,
  useReorderPropertyImages,
  useSetPropertyImageHero,
} from "../hooks";
import {
  PROPERTY_IMAGE_KINDS,
  type PropertyDetail,
  type PropertyImage,
  type PropertyImageKind,
} from "../schemas";
import { PropertyImageFormDialog } from "../components/PropertyImageFormDialog";

interface MediaContext {
  property: PropertyDetail;
}

interface ImageCardProps {
  image: PropertyImage;
  canWrite: boolean;
  onSetHero: (image: PropertyImage) => void;
  onEdit: (image: PropertyImage) => void;
  onDelete: (image: PropertyImage) => void;
}

function ImageCard({ image, canWrite, onSetHero, onEdit, onDelete }: ImageCardProps) {
  const { t } = useTranslation("properties");
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: image.id,
    disabled: !canWrite,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  const isHero = image.kind === "hero";
  const kindKey = (PROPERTY_IMAGE_KINDS as readonly string[]).includes(image.kind)
    ? (image.kind as PropertyImageKind)
    : null;
  const kindLabel = kindKey ? t(`image_kinds.${kindKey}`) : image.kind;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "border-border bg-card flex flex-col overflow-hidden rounded-lg border",
        isDragging && "opacity-60",
        isHero && "ring-foreground ring-2",
      )}
      data-testid={`property-image-card-${image.id}`}
    >
      <div
        className="bg-muted relative aspect-[4/3] w-full"
        {...(canWrite ? { ...attributes, ...listeners } : {})}
        aria-label={canWrite ? t("media.card.drag_handle_label") : undefined}
        role={canWrite ? "button" : undefined}
      >
        {image.image ? (
          <img
            src={image.image}
            alt={image.name ?? ""}
            className="h-full w-full object-cover"
            draggable={false}
          />
        ) : (
          <div className="text-muted-foreground flex h-full w-full items-center justify-center text-xs">
            {t("media.card.no_thumbnail")}
          </div>
        )}
      </div>
      <div className="flex items-start justify-between gap-2 p-3">
        <div className="min-w-0">
          <p className="text-foreground truncate text-sm font-medium">
            {image.name?.trim() || image.image || `#${image.id}`}
          </p>
          <div className="mt-1 flex items-center gap-2">
            {isHero ? (
              <Badge variant="default">{t("media.card.hero_badge")}</Badge>
            ) : (
              <Badge variant="outline">{kindLabel}</Badge>
            )}
            {image.is_active === false ? (
              <Badge variant="outline">{t("media.card.inactive_badge")}</Badge>
            ) : null}
          </div>
        </div>
        {canWrite ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                aria-label={t("media.card.menu_label")}
              >
                ···
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {!isHero ? (
                <DropdownMenuItem onClick={() => onSetHero(image)}>
                  {t("media.card.set_hero")}
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem onClick={() => onEdit(image)}>
                {t("media.card.edit")}
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive" onClick={() => onDelete(image)}>
                {t("media.card.delete")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </div>
  );
}

export function MediaTab() {
  const { property } = useOutletContext<MediaContext>();
  const { t } = useTranslation("properties");
  const propertyId = property.id;
  const canWrite = useHasReservationsRole();
  const images = usePropertyImages(propertyId);
  const reorderMutation = useReorderPropertyImages(propertyId);
  const setHeroMutation = useSetPropertyImageHero(propertyId);
  const deleteMutation = useDeletePropertyImage(propertyId);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [localOrder, setLocalOrder] = useState<PropertyImage[] | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<PropertyImage | null>(null);
  const [deleting, setDeleting] = useState<PropertyImage | null>(null);

  const serverImages = useMemo(() => images.data?.results ?? [], [images.data?.results]);
  const displayed = localOrder ?? serverImages;

  useEffect(() => {
    // Reset optimistic order when the server delivers a fresh page.
    setLocalOrder(null);
  }, [serverImages]);

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = displayed.findIndex((i) => i.id === active.id);
    const newIndex = displayed.findIndex((i) => i.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(displayed, oldIndex, newIndex);
    setLocalOrder(next);
    try {
      await reorderMutation.mutateAsync(next.map((i) => i.id));
      toast.success(t("media.toasts.reordered"));
    } catch {
      setLocalOrder(null);
      toast.error(t("media.toasts.reorder_failed"));
    }
  };

  const handleSetHero = async (image: PropertyImage) => {
    try {
      await setHeroMutation.mutateAsync({ imageId: image.id });
      toast.success(t("media.toasts.hero_set"));
    } catch (error) {
      if (error instanceof ApiError) {
        toast.error(error.detail);
      } else {
        toast.error(t("media.toasts.update_failed"));
      }
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ imageId: deleting.id });
      toast.success(t("media.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("media.toasts.delete_failed"));
    }
  };

  if (images.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-40" />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[4/3] w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (images.isError) {
    return (
      <div className="p-6">
        <ErrorState
          description={t("media.errors.load_failed")}
          onRetry={() => images.refetch()}
          retrying={images.isFetching}
        />
      </div>
    );
  }

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setAddOpen(true)}>
      {t("media.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("media.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("media.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("media.title")}</h2>
        {addButton}
      </div>

      {displayed.length === 0 ? (
        <EmptyState title={t("media.empty.title")} description={t("media.empty.description")} />
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <SortableContext items={displayed.map((i) => i.id)} strategy={rectSortingStrategy}>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
              {displayed.map((image) => (
                <ImageCard
                  key={image.id}
                  image={image}
                  canWrite={canWrite}
                  onSetHero={handleSetHero}
                  onEdit={setEditing}
                  onDelete={setDeleting}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {addOpen ? (
        <PropertyImageFormDialog
          propertyId={propertyId}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <PropertyImageFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          image={editing}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("media.delete_confirm.title")}
          description={t("media.delete_confirm.description")}
          confirmLabel={t("media.delete_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
