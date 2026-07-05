import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { toast } from "sonner";
import { DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, useSortable } from "@dnd-kit/sortable";
import { verticalListSortingStrategy } from "@dnd-kit/sortable";
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
import { FeatureIcon } from "@/components/data/FeatureIcon";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { cn } from "@/lib/cn";
import { useDeletePropertyRoom, usePropertyRooms, useReorderPropertyRooms } from "../hooks";
import type { PropertyDetail, PropertyRoom, RoomBeds } from "../schemas";
import { RoomFormDialog } from "../components/RoomFormDialog";

interface RoomsContext {
  property: PropertyDetail;
}

function bedSummary(beds: RoomBeds | undefined, t: TFunction<"properties">): string {
  if (!beds) return t("rooms.row.no_beds");
  const parts: string[] = [];
  if (beds.double) parts.push(t("rooms.row.beds_count.double", { count: beds.double }));
  if (beds.twin_double)
    parts.push(t("rooms.row.beds_count.twin_double", { count: beds.twin_double }));
  if (beds.twin) parts.push(t("rooms.row.beds_count.twin", { count: beds.twin }));
  if (beds.single) parts.push(t("rooms.row.beds_count.single", { count: beds.single }));
  if (beds.bunk) parts.push(t("rooms.row.beds_count.bunk", { count: beds.bunk }));
  if (beds.sofa) parts.push(t("rooms.row.beds_count.sofa", { count: beds.sofa }));
  if (beds.childrens) parts.push(t("rooms.row.beds_count.childrens", { count: beds.childrens }));
  return parts.length ? parts.join(" · ") : t("rooms.row.no_beds");
}

interface RoomRowProps {
  room: PropertyRoom;
  canWrite: boolean;
  onEdit: (room: PropertyRoom) => void;
  onDelete: (room: PropertyRoom) => void;
}

function RoomRow({ room, canWrite, onEdit, onDelete }: RoomRowProps) {
  const { t } = useTranslation("properties");
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: room.id,
    disabled: !canWrite,
  });
  const style = { transform: CSS.Transform.toString(transform), transition };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={cn(
        "border-border bg-card flex items-center justify-between gap-4 rounded-lg border p-3",
        isDragging && "opacity-60",
      )}
      data-testid={`property-room-row-${room.id}`}
    >
      <div
        className="flex min-w-0 flex-1 items-start gap-3"
        {...(canWrite ? { ...attributes, ...listeners } : {})}
        aria-label={canWrite ? t("rooms.row.drag_handle_label") : undefined}
        role={canWrite ? "button" : undefined}
      >
        <div className="text-muted-foreground px-1 select-none">⋮⋮</div>
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-foreground truncate font-medium">{room.name}</p>
            <Badge variant="outline">{t(`rooms.placements.${room.placement}`)}</Badge>
            {room.is_ensuite ? (
              <Badge variant="secondary">
                {room.ensuite_type
                  ? t("rooms.row.ensuite_with_type", {
                      type: t(`rooms.ensuite_types.${room.ensuite_type}`),
                    })
                  : t("rooms.row.ensuite")}
              </Badge>
            ) : null}
            {room.access ? (
              <Badge variant="outline">{t(`rooms.access_types.${room.access}`)}</Badge>
            ) : null}
          </div>
          <p className="text-muted-foreground text-sm">{bedSummary(room.beds, t)}</p>
          {room.attribute_links.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              {room.attribute_links.map((link) => (
                <span
                  key={link.id}
                  className="border-border text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
                >
                  <FeatureIcon name={link.icon} className="size-3" />
                  {link.name}
                </span>
              ))}
            </div>
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
              aria-label={t("rooms.row.menu_label")}
            >
              ···
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(room)}>{t("rooms.row.edit")}</DropdownMenuItem>
            <DropdownMenuItem className="text-destructive" onClick={() => onDelete(room)}>
              {t("rooms.row.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </li>
  );
}

export function RoomsTab() {
  const { property } = useOutletContext<RoomsContext>();
  const { t } = useTranslation("properties");
  const propertyId = property.id;
  const canWrite = useHasReservationsRole();
  const rooms = usePropertyRooms(propertyId);
  const reorderMutation = useReorderPropertyRooms(propertyId);
  const deleteMutation = useDeletePropertyRoom(propertyId);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [localOrder, setLocalOrder] = useState<PropertyRoom[] | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<PropertyRoom | null>(null);
  const [deleting, setDeleting] = useState<PropertyRoom | null>(null);

  const serverRooms = useMemo(() => rooms.data?.results ?? [], [rooms.data?.results]);
  const displayed = localOrder ?? serverRooms;

  useEffect(() => {
    setLocalOrder(null);
  }, [serverRooms]);

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = displayed.findIndex((r) => r.id === active.id);
    const newIndex = displayed.findIndex((r) => r.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(displayed, oldIndex, newIndex);
    setLocalOrder(next);
    try {
      await reorderMutation.mutateAsync(next.map((r) => r.id));
      toast.success(t("rooms.toasts.reordered"));
    } catch {
      setLocalOrder(null);
      toast.error(t("rooms.toasts.reorder_failed"));
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ roomId: deleting.id });
      toast.success(t("rooms.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("rooms.toasts.delete_failed"));
    }
  };

  if (rooms.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (rooms.isError) {
    return (
      <div className="p-6">
        <ErrorState
          description={t("rooms.errors.load_failed")}
          onRetry={() => rooms.refetch()}
          retrying={rooms.isFetching}
        />
      </div>
    );
  }

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setAddOpen(true)}>
      {t("rooms.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("rooms.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("rooms.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("rooms.title")}</h2>
        {addButton}
      </div>

      {displayed.length === 0 ? (
        <EmptyState title={t("rooms.empty.title")} description={t("rooms.empty.description")} />
      ) : (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <SortableContext
            items={displayed.map((r) => r.id)}
            strategy={verticalListSortingStrategy}
          >
            <ul className="space-y-2">
              {displayed.map((room) => (
                <RoomRow
                  key={room.id}
                  room={room}
                  canWrite={canWrite}
                  onEdit={setEditing}
                  onDelete={setDeleting}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      )}

      {addOpen ? (
        <RoomFormDialog
          propertyId={propertyId}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <RoomFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          room={editing}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("rooms.delete_confirm.title")}
          description={t("rooms.delete_confirm.description")}
          confirmLabel={t("rooms.delete_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
