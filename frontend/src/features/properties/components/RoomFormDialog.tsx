import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
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
import { useCreatePropertyRoom, useUpdatePropertyRoom } from "../hooks";
import {
  ROOM_PLACEMENTS,
  propertyRoomWriteInputSchema,
  type PropertyRoom,
  type PropertyRoomWriteInput,
  type RoomPlacement,
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
  room: PropertyRoom;
}

type RoomFormDialogProps = CreateProps | EditProps;

const EMPTY_BEDS = {
  double: 0,
  twin_double: 0,
  twin: 0,
  single: 0,
  bunk: 0,
  sofa: 0,
  childrens: 0,
};

const CREATE_DEFAULTS: PropertyRoomWriteInput = {
  name: "",
  placement: "main_house",
  website_description: "",
  vc_notes: "",
  is_ensuite: false,
  beds: EMPTY_BEDS,
};

function defaultsFromRoom(room: PropertyRoom): PropertyRoomWriteInput {
  return {
    name: room.name,
    placement: room.placement,
    website_description: room.website_description ?? "",
    vc_notes: room.vc_notes ?? "",
    is_ensuite: room.is_ensuite,
    beds: room.beds ?? { ...EMPTY_BEDS },
  };
}

const BED_FIELDS = [
  "double",
  "twin_double",
  "twin",
  "single",
  "bunk",
  "sofa",
  "childrens",
] as const;

export function RoomFormDialog(props: RoomFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const form = useForm<PropertyRoomWriteInput>({
    resolver: zodResolver(propertyRoomWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromRoom(props.room),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreatePropertyRoom(propertyId);
  const updateMutation = useUpdatePropertyRoom(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromRoom(props.room));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.room.id]);

  const handleSubmit = async (values: PropertyRoomWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("rooms.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ roomId: props.room.id, input: values });
        toast.success(t("rooms.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(isCreate ? t("rooms.toasts.create_failed") : t("rooms.toasts.update_failed"));
      }
    }
  };

  const placement = form.watch("placement");
  const isEnsuite = form.watch("is_ensuite") ?? false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("rooms.dialog.create_title") : t("rooms.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="property-room-name">{t("rooms.dialog.fields.name")}</Label>
            <Input
              id="property-room-name"
              placeholder={t("rooms.dialog.fields.name_placeholder")}
              {...form.register("name")}
            />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {String(form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="property-room-placement">{t("rooms.dialog.fields.placement")}</Label>
            <Select
              value={placement}
              onValueChange={(v) => form.setValue("placement", v as RoomPlacement)}
            >
              <SelectTrigger id="property-room-placement">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROOM_PLACEMENTS.map((p) => (
                  <SelectItem key={p} value={p}>
                    {t(`rooms.placements.${p}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="property-room-ensuite"
              checked={isEnsuite}
              onCheckedChange={(v) => form.setValue("is_ensuite", v === true)}
            />
            <Label htmlFor="property-room-ensuite">{t("rooms.dialog.fields.is_ensuite")}</Label>
          </div>

          <fieldset className="border-border space-y-2 rounded-md border p-3">
            <legend className="text-foreground px-1 text-sm font-medium">
              {t("rooms.dialog.fields.beds")}
            </legend>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {BED_FIELDS.map((bed) => (
                <div key={bed} className="space-y-1">
                  <Label htmlFor={`property-room-beds-${bed}`} className="text-xs">
                    {t(`rooms.beds.${bed}`)}
                  </Label>
                  <Input
                    id={`property-room-beds-${bed}`}
                    type="number"
                    min={0}
                    step={1}
                    {...form.register(`beds.${bed}`, { valueAsNumber: true })}
                  />
                </div>
              ))}
            </div>
          </fieldset>

          <div className="space-y-2">
            <Label htmlFor="property-room-website-description">
              {t("rooms.dialog.fields.website_description")}
            </Label>
            <Textarea
              id="property-room-website-description"
              rows={3}
              {...form.register("website_description")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="property-room-vc-notes">{t("rooms.dialog.fields.vc_notes")}</Label>
            <Textarea id="property-room-vc-notes" rows={2} {...form.register("vc_notes")} />
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
              {t("rooms.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("rooms.dialog.actions.saving") : t("rooms.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
