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
import { useCreatePropertyImage, useUpdatePropertyImage } from "../hooks";
import {
  PROPERTY_IMAGE_KINDS,
  propertyImageCreateInputSchema,
  propertyImageMetadataSchema,
  type PropertyImage,
  type PropertyImageKind,
  type PropertyImageCreateInput,
  type PropertyImageMetadataInput,
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
  image: PropertyImage;
}

type PropertyImageFormDialogProps = CreateProps | EditProps;

// Create-mode values; `image` stays unset until the user picks a file (the
// create schema then requires it). Edit mode reuses the same shape minus the
// file, validated against the metadata-only schema.
type FormValues = PropertyImageMetadataInput & { image?: File };

const CREATE_DEFAULTS: FormValues = {
  kind: "gallery",
  name: "",
  description: "",
};

function defaultsFromImage(image: PropertyImage): FormValues {
  const kind = (PROPERTY_IMAGE_KINDS as readonly string[]).includes(image.kind)
    ? (image.kind as PropertyImageKind)
    : "gallery";
  return {
    kind,
    name: image.name ?? "",
    description: image.description ?? "",
    sort_order: image.sort_order ?? undefined,
    is_active: image.is_active ?? true,
  };
}

export function PropertyImageFormDialog(props: PropertyImageFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const form = useForm<FormValues>({
    resolver: zodResolver(isCreate ? propertyImageCreateInputSchema : propertyImageMetadataSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromImage(props.image),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreatePropertyImage(propertyId);
  const updateMutation = useUpdatePropertyImage(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromImage(props.image));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.image.id]);

  const handleSubmit = async (values: FormValues) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        // The create-mode resolver guarantees `image` is a File here.
        await createMutation.mutateAsync(values as PropertyImageCreateInput);
        toast.success(t("media.toasts.created"));
      } else {
        const { kind, name, description, sort_order, is_active } = values;
        await updateMutation.mutateAsync({
          imageId: props.image.id,
          input: { kind, name, description, sort_order, is_active },
        });
        toast.success(t("media.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(isCreate ? t("media.toasts.create_failed") : t("media.toasts.update_failed"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("media.dialog.create_title") : t("media.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          {isCreate ? (
            <div className="space-y-2">
              <Label htmlFor="property-image-file">{t("media.dialog.fields.file")}</Label>
              <Input
                id="property-image-file"
                type="file"
                accept="image/*"
                onChange={(e) =>
                  form.setValue("image", e.target.files?.[0], { shouldValidate: true })
                }
              />
              {form.formState.errors.image ? (
                <p className="text-destructive text-sm" role="alert">
                  {t("errors.image_file_required")}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="property-image-kind">{t("media.dialog.fields.kind")}</Label>
            <Select
              value={form.watch("kind")}
              onValueChange={(v) => form.setValue("kind", v as PropertyImageKind)}
            >
              <SelectTrigger id="property-image-kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROPERTY_IMAGE_KINDS.map((k) => (
                  <SelectItem key={k} value={k}>
                    {t(`image_kinds.${k}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="property-image-name">{t("media.dialog.fields.name")}</Label>
            <Input
              id="property-image-name"
              placeholder={t("media.dialog.fields.name_placeholder")}
              {...form.register("name")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="property-image-description">
              {t("media.dialog.fields.description")}
            </Label>
            <Textarea
              id="property-image-description"
              placeholder={t("media.dialog.fields.description_placeholder")}
              rows={3}
              {...form.register("description")}
            />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("media.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("media.dialog.actions.saving") : t("media.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
