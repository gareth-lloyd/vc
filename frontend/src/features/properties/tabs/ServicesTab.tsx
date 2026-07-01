import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ChevronDown, ChevronUp } from "lucide-react";
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
import { useDeletePropertyService, usePropertyServices, useUpdatePropertyService } from "../hooks";
import type { PropertyDetail, PropertyService } from "../schemas";
import { ServiceFormDialog } from "../components/ServiceFormDialog";

interface ServicesContext {
  property: PropertyDetail;
}

export function ServicesTab() {
  const { property } = useOutletContext<ServicesContext>();
  const { t } = useTranslation("properties");
  const propertyId = property.id;
  const canWrite = useHasReservationsRole();
  const services = usePropertyServices(propertyId);
  const updateMutation = useUpdatePropertyService(propertyId);
  const deleteMutation = useDeletePropertyService(propertyId);

  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<PropertyService | null>(null);
  const [deleting, setDeleting] = useState<PropertyService | null>(null);

  const sorted = useMemo(() => {
    const rows = services.data?.results ?? [];
    return [...rows].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
  }, [services.data?.results]);

  const formatBand = (service: PropertyService): string => {
    if (!service.applies_from && !service.applies_to) return t("services.row.year_round");
    const open = t("services.row.open_end");
    return t("services.row.band", {
      from: service.applies_from ?? open,
      to: service.applies_to ?? open,
    });
  };

  const handleMove = async (index: number, direction: -1 | 1) => {
    const target = sorted[index];
    const neighbor = sorted[index + direction];
    if (!target || !neighbor) return;
    try {
      await Promise.all([
        updateMutation.mutateAsync({
          serviceId: target.id,
          input: { sort_order: neighbor.sort_order },
        }),
        updateMutation.mutateAsync({
          serviceId: neighbor.id,
          input: { sort_order: target.sort_order },
        }),
      ]);
      toast.success(t("services.toasts.reordered"));
    } catch {
      toast.error(t("services.toasts.reorder_failed"));
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteMutation.mutateAsync({ serviceId: deleting.id });
      toast.success(t("services.toasts.deleted"));
      setDeleting(null);
    } catch {
      toast.error(t("services.toasts.delete_failed"));
    }
  };

  if (services.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (services.isError) {
    return (
      <div className="p-6">
        <ErrorState
          description={t("services.errors.load_failed")}
          onRetry={() => services.refetch()}
          retrying={services.isFetching}
        />
      </div>
    );
  }

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setAddOpen(true)}>
      {t("services.add_button")}
    </Button>
  ) : (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>
          <Button size="sm" disabled>
            {t("services.add_button")}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>{t("services.add_button_disabled_tooltip")}</TooltipContent>
    </Tooltip>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("services.title")}</h2>
        {addButton}
      </div>

      {sorted.length === 0 ? (
        <EmptyState
          title={t("services.empty.title")}
          description={t("services.empty.description")}
        />
      ) : (
        <ul className="space-y-2">
          {sorted.map((service, index) => {
            const isFirst = index === 0;
            const isLast = index === sorted.length - 1;
            return (
              <li
                key={service.id}
                className="border-border bg-card flex items-center justify-between gap-3 rounded-lg border p-3"
                data-testid={`property-service-row-${service.id}`}
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-foreground truncate font-medium">{service.name}</p>
                    {!service.is_active ? (
                      <Badge variant="outline">{t("services.row.inactive")}</Badge>
                    ) : null}
                  </div>
                  <p className="text-muted-foreground text-sm">{formatBand(service)}</p>
                  {service.copy ? (
                    <p className="text-muted-foreground truncate text-xs">{service.copy}</p>
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
                      aria-label={t("services.row.move_up")}
                    >
                      <ChevronUp className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      disabled={isLast || updateMutation.isPending}
                      onClick={() => handleMove(index, 1)}
                      aria-label={t("services.row.move_down")}
                    >
                      <ChevronDown className="size-4" />
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2"
                          aria-label={t("services.row.menu_label")}
                        >
                          ···
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditing(service)}>
                          {t("services.row.edit")}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => setDeleting(service)}
                        >
                          {t("services.row.delete")}
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
        <ServiceFormDialog
          propertyId={propertyId}
          open={addOpen}
          onOpenChange={setAddOpen}
          mode="create"
        />
      ) : null}
      {editing ? (
        <ServiceFormDialog
          propertyId={propertyId}
          open={!!editing}
          onOpenChange={(o) => !o && setEditing(null)}
          mode="edit"
          service={editing}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          onConfirm={handleDelete}
          title={t("services.delete_confirm.title")}
          description={t("services.delete_confirm.description")}
          confirmLabel={t("services.delete_confirm.confirm")}
          destructive
          busy={deleteMutation.isPending}
        />
      ) : null}
    </div>
  );
}
