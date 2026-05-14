import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import {
  useCreatePropertyNearbyPlace,
  useNearbyPlaceTypes,
  useUpdatePropertyNearbyPlace,
} from "../hooks";
import {
  propertyNearbyPlaceWriteInputSchema,
  type PropertyNearbyPlace,
  type PropertyNearbyPlaceWriteInput,
} from "../schemas";

interface CommonProps {
  propertyId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  place: PropertyNearbyPlace;
}

type NearbyPlaceFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: PropertyNearbyPlaceWriteInput = {
  place_type: 0,
  name: "",
  distance_km: "",
  notes: "",
};

function defaultsFromPlace(place: PropertyNearbyPlace): PropertyNearbyPlaceWriteInput {
  return {
    place_type: place.place_type,
    name: place.name,
    distance_km: place.distance_km,
    notes: place.notes ?? "",
  };
}

export function NearbyPlaceFormDialog(props: NearbyPlaceFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const placeTypes = useNearbyPlaceTypes();

  const form = useForm<PropertyNearbyPlaceWriteInput>({
    resolver: zodResolver(propertyNearbyPlaceWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromPlace(props.place),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreatePropertyNearbyPlace(propertyId);
  const updateMutation = useUpdatePropertyNearbyPlace(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromPlace(props.place));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.place.id]);

  const handleSubmit = async (values: PropertyNearbyPlaceWriteInput) => {
    setTopLevelError(null);
    if (!values.place_type) {
      form.setError("place_type", { message: t("errors.nearby_type_required") });
      return;
    }
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("nearby.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ poiId: props.place.id, input: values });
        toast.success(t("nearby.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(isCreate ? t("nearby.toasts.create_failed") : t("nearby.toasts.update_failed"));
      }
    }
  };

  const placeTypeValue = form.watch("place_type");
  const placeTypeOptions = placeTypes.data?.results ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("nearby.dialog.create_title") : t("nearby.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="property-nearby-type">{t("nearby.dialog.fields.place_type")}</Label>
            <Select
              value={placeTypeValue ? String(placeTypeValue) : ""}
              onValueChange={(v) => form.setValue("place_type", Number(v))}
            >
              <SelectTrigger id="property-nearby-type">
                <SelectValue placeholder={t("nearby.dialog.fields.place_type_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                {placeTypeOptions.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.place_type ? (
              <p className="text-destructive text-sm" role="alert">
                {String(form.formState.errors.place_type.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="property-nearby-name">{t("nearby.dialog.fields.name")}</Label>
            <Input
              id="property-nearby-name"
              placeholder={t("nearby.dialog.fields.name_placeholder")}
              {...form.register("name")}
            />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {String(form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="property-nearby-distance">
              {t("nearby.dialog.fields.distance_km")}
            </Label>
            <Input
              id="property-nearby-distance"
              inputMode="decimal"
              placeholder={t("nearby.dialog.fields.distance_km_placeholder")}
              {...form.register("distance_km")}
            />
            {form.formState.errors.distance_km ? (
              <p className="text-destructive text-sm" role="alert">
                {String(form.formState.errors.distance_km.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="property-nearby-notes">{t("nearby.dialog.fields.notes")}</Label>
            <Textarea id="property-nearby-notes" rows={2} {...form.register("notes")} />
          </div>

          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("nearby.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("nearby.dialog.actions.saving") : t("nearby.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
