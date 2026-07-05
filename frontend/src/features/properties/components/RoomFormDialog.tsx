import { useEffect, useState } from "react";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
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
import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { cn } from "@/lib/cn";
import { useCreatePropertyRoom, useRoomAttributes, useUpdatePropertyRoom } from "../hooks";
import {
  ENSUITE_TYPES,
  ROOM_ACCESS,
  ROOM_PLACEMENTS,
  propertyRoomWriteInputSchema,
  type EnsuiteType,
  type PropertyRoom,
  type PropertyRoomWriteInput,
  type RoomAccess,
  type RoomPlacement,
} from "../schemas";
import { fieldErrorText } from "@/lib/forms/fieldError";

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
  ensuite_type: "",
  access: "",
  beds: EMPTY_BEDS,
  attribute_links: [],
};

function defaultsFromRoom(room: PropertyRoom): PropertyRoomWriteInput {
  return {
    name: room.name,
    placement: room.placement,
    website_description: room.website_description ?? "",
    vc_notes: room.vc_notes ?? "",
    is_ensuite: room.is_ensuite,
    ensuite_type: room.ensuite_type ?? "",
    access: room.access ?? "",
    beds: room.beds ?? { ...EMPTY_BEDS },
    // Seed EVERY existing link — including retired (is_active=false) ones — so
    // a full-list save never silently drops an assignment the user didn't
    // untick (review-blocker B1).
    attribute_links: (room.attribute_links ?? []).map((link) => ({
      attribute: link.attribute,
      note: link.note ?? "",
    })),
  };
}

// shadcn/radix Select forbids an empty-string item value, so the blank
// ("unknown" / "not specified") option rides a sentinel that maps to `""` on
// the way in/out of the form.
const ENSUITE_TYPE_NONE = "unknown";
const ACCESS_NONE = "unspecified";

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
  const attributesQuery = useRoomAttributes();

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
  const ensuiteType = form.watch("ensuite_type") ?? "";
  const access = form.watch("access") ?? "";
  const attributeLinks = form.watch("attribute_links") ?? [];

  // Render the active catalog ∪ the attributes already assigned to this room.
  // Retired (is_active=false) but-assigned rows stay visible — muted, badged
  // "Retired", and still ticked so the full-list save keeps them (B1).
  const catalogRows = attributesQuery.data?.results ?? [];
  const assignedLinks = isCreate ? [] : props.room.attribute_links;
  const amenityRows: { id: number; name: string; is_active: boolean }[] = [];
  for (const attr of catalogRows) {
    if (attr.is_active) amenityRows.push({ id: attr.id, name: attr.name, is_active: true });
  }
  for (const link of assignedLinks) {
    if (!amenityRows.some((row) => row.id === link.attribute)) {
      amenityRows.push({ id: link.attribute, name: link.name, is_active: link.is_active });
    }
  }

  const toggleAttribute = (attributeId: number, checked: boolean) => {
    const current = form.getValues("attribute_links") ?? [];
    if (checked) {
      if (!current.some((l) => l.attribute === attributeId)) {
        form.setValue("attribute_links", [...current, { attribute: attributeId, note: "" }]);
      }
    } else {
      form.setValue(
        "attribute_links",
        current.filter((l) => l.attribute !== attributeId),
      );
    }
  };

  const setAttributeNote = (attributeId: number, note: string) => {
    const current = form.getValues("attribute_links") ?? [];
    form.setValue(
      "attribute_links",
      current.map((l) => (l.attribute === attributeId ? { ...l, note } : l)),
    );
  };

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
                {fieldErrorText(t, form.formState.errors.name.message)}
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
              onCheckedChange={(v) => {
                const checked = v === true;
                form.setValue("is_ensuite", checked);
                // Unchecking ensuite makes a lingering ensuite type nonsense —
                // and the server would flip is_ensuite straight back on.
                if (!checked) form.setValue("ensuite_type", "");
              }}
            />
            <Label htmlFor="property-room-ensuite">{t("rooms.dialog.fields.is_ensuite")}</Label>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="property-room-ensuite-type">
                {t("rooms.dialog.fields.ensuite_type")}
              </Label>
              <Select
                value={ensuiteType === "" ? ENSUITE_TYPE_NONE : ensuiteType}
                onValueChange={(v) => {
                  if (v === ENSUITE_TYPE_NONE) {
                    form.setValue("ensuite_type", "");
                  } else {
                    form.setValue("ensuite_type", v as EnsuiteType);
                    // Mirror the server rule: a concrete ensuite type implies
                    // the room IS ensuite.
                    form.setValue("is_ensuite", true);
                  }
                }}
              >
                <SelectTrigger id="property-room-ensuite-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ENSUITE_TYPE_NONE}>
                    {t("rooms.ensuite_types.unknown")}
                  </SelectItem>
                  {ENSUITE_TYPES.map((et) => (
                    <SelectItem key={et} value={et}>
                      {t(`rooms.ensuite_types.${et}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="property-room-access">{t("rooms.dialog.fields.access")}</Label>
              <Select
                value={access === "" ? ACCESS_NONE : access}
                onValueChange={(v) =>
                  form.setValue("access", v === ACCESS_NONE ? "" : (v as RoomAccess))
                }
              >
                <SelectTrigger id="property-room-access">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ACCESS_NONE}>{t("rooms.access_types.unspecified")}</SelectItem>
                  {ROOM_ACCESS.map((a) => (
                    <SelectItem key={a} value={a}>
                      {t(`rooms.access_types.${a}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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

          {amenityRows.length > 0 ? (
            <fieldset className="border-border space-y-2 rounded-md border p-3">
              <legend className="text-foreground px-1 text-sm font-medium">
                {t("rooms.dialog.fields.amenities")}
              </legend>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {amenityRows.map((attr) => {
                  const link = attributeLinks.find((l) => l.attribute === attr.id);
                  return (
                    <div key={attr.id} className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Checkbox
                          id={`property-room-attribute-${attr.id}`}
                          checked={!!link}
                          onCheckedChange={(v) => toggleAttribute(attr.id, v === true)}
                        />
                        <Label
                          htmlFor={`property-room-attribute-${attr.id}`}
                          className={cn(!attr.is_active && "text-muted-foreground")}
                        >
                          {attr.name}
                        </Label>
                        {!attr.is_active ? (
                          <Badge variant="outline" className="text-muted-foreground">
                            {t("rooms.dialog.retired_badge")}
                          </Badge>
                        ) : null}
                      </div>
                      {link ? (
                        <Input
                          className="h-8"
                          aria-label={t("rooms.dialog.fields.amenity_note_placeholder")}
                          placeholder={t("rooms.dialog.fields.amenity_note_placeholder")}
                          value={link.note ?? ""}
                          onChange={(e) => setAttributeNote(attr.id, e.target.value)}
                        />
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </fieldset>
          ) : null}

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

          <FormErrorAlert message={topLevelError} />

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
