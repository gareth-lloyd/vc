import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ChevronDown, ChevronUp } from "lucide-react";
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
import {
  useDeletePropertyNearbyPlace,
  useNearbyPlaceTypes,
  usePropertyNearbyPlaces,
  useUpdatePropertyNearbyPlace,
} from "../hooks";
import type { PropertyDetail, PropertyNearbyPlace } from "../schemas";
import { NearbyPlaceFormDialog } from "../components/NearbyPlaceFormDialog";

interface NearbyContext {
  property: PropertyDetail;
}

export function NearbyTab() {
  const { property } = useOutletContext<NearbyContext>();
  const { t } = useTranslation("properties");
  const propertyId = property.id;
  const canWrite = useHasReservationsRole();
  const places = usePropertyNearbyPlaces(propertyId);
  const placeTypes = useNearbyPlaceTypes();
  const updateMutation = useUpdatePropertyNearbyPlace(propertyId);
  const deleteMutation = useDeletePropertyNearbyPlace(propertyId);

  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<PropertyNearbyPlace | null>(null);
  const [deleting, setDeleting] = useState<PropertyNearbyPlace | null>(null);

  const placeTypesById = useMemo(() => {
    const map = new Map<number, string>();
    for (const pt of placeTypes.data?.results ?? []) {
      map.set(pt.id, pt.name);
    }
    return map;
  }, [placeTypes.data?.results]);

  const sorted = useMemo(() => {
    const rows = places.data?.results ?? [];
    return [...rows].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
  }, [places.data?.results]);

  const handleMove = async (index: number, direction: -1 | 1) => {
    const target = sorted[index];
    const neighbor = sorted[index + direction];
    if (!target || !neighbor) return;
    try {
      await Promise.all([
        updateMutation.mutateAsync({
          poiId: target.id,
          input: { sort_order: neighbor.sort_order },
        }),
        updateMutation.mutateAsync({
          poiId: neighbor.id,
          input: { sort_order: target.sort_order },
        }),
      ]);
      toast.success(t("nearby.toasts.reordered"));
    } catch {
      toast.error(t("nearby.toasts.reorder_failed"));
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ poiId: deleting.id });
      toast.success(t("nearby.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("nearby.toasts.delete_failed"));
    }
  };

  if (places.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (places.isError) {
    return (
      <div className="p-6">
        <ErrorState
          description={t("nearby.errors.load_failed")}
          onRetry={() => places.refetch()}
          retrying={places.isFetching}
        />
      </div>
    );
  }

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setAddOpen(true)}>
      {t("nearby.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("nearby.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("nearby.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("nearby.title")}</h2>
        {addButton}
      </div>

      {sorted.length === 0 ? (
        <EmptyState title={t("nearby.empty.title")} description={t("nearby.empty.description")} />
      ) : (
        <ul className="space-y-2">
          {sorted.map((place, index) => {
            const typeName = placeTypesById.get(place.place_type) ?? t("nearby.row.unknown_type");
            const isFirst = index === 0;
            const isLast = index === sorted.length - 1;
            return (
              <li
                key={place.id}
                className="border-border bg-card flex items-center justify-between gap-3 rounded-lg border p-3"
                data-testid={`property-nearby-row-${place.id}`}
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="text-foreground truncate font-medium">{place.name}</p>
                  <p className="text-muted-foreground text-sm">
                    {typeName} ·{" "}
                    {t("nearby.row.distance_km", { distance: Number(place.distance_km) })}
                  </p>
                  {place.notes ? (
                    <p className="text-muted-foreground truncate text-xs">{place.notes}</p>
                  ) : null}
                </div>
                {canWrite ? (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      disabled={isFirst || updateMutation.isPending}
                      onClick={() => handleMove(index, -1)}
                      aria-label={t("nearby.row.move_up")}
                    >
                      <ChevronUp className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      disabled={isLast || updateMutation.isPending}
                      onClick={() => handleMove(index, 1)}
                      aria-label={t("nearby.row.move_down")}
                    >
                      <ChevronDown className="size-4" />
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2"
                          aria-label={t("nearby.row.menu_label")}
                        >
                          ···
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditing(place)}>
                          {t("nearby.row.edit")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => setDeleting(place)}
                        >
                          {t("nearby.row.delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {addOpen ? (
        <NearbyPlaceFormDialog
          propertyId={propertyId}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <NearbyPlaceFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          place={editing}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("nearby.delete_confirm.title")}
          description={t("nearby.delete_confirm.description")}
          confirmLabel={t("nearby.delete_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
