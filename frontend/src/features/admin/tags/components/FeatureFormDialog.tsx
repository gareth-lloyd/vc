import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import {
  FEATURE_SERVICE_TYPES,
  featureWriteInputSchema,
  type Feature,
  type FeatureCategory,
  type FeatureServiceType,
  type FeatureWriteInput,
} from "../schemas";
import { useCreateFeature, useUpdateFeature } from "../hooks";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { IconPicker } from "@/components/data/IconPicker";
import { fieldErrorText } from "@/lib/forms/fieldError";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: FeatureCategory[];
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  feature: Feature;
}

type Props = CreateProps | EditProps;

function createDefaults(categories: FeatureCategory[]): FeatureWriteInput {
  return {
    category: categories[0]?.id ?? 0,
    name: "",
    slug: "",
    description: "",
    icon: "",
    sort_order: 0,
    is_active: true,
    service_type: "amenity",
  };
}

function editDefaults(f: Feature): FeatureWriteInput {
  const st = (FEATURE_SERVICE_TYPES as string[]).includes(f.service_type)
    ? (f.service_type as FeatureServiceType)
    : ("amenity" as FeatureServiceType);
  return {
    category: f.category,
    name: f.name,
    slug: f.slug,
    description: f.description ?? "",
    icon: f.icon ?? "",
    sort_order: f.sort_order ?? 0,
    is_active: f.is_active,
    service_type: st,
  };
}

export function FeatureFormDialog(props: Props) {
  const { open, onOpenChange, categories } = props;
  const isCreate = props.mode === "create";
  const { t } = useTranslation("admin");

  const form = useForm<FeatureWriteInput>({
    resolver: zodResolver(featureWriteInputSchema),
    defaultValues: isCreate ? createDefaults(categories) : editDefaults(props.feature),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const createMutation = useCreateFeature();
  const updateMutation = useUpdateFeature(isCreate ? 0 : props.feature.id);
  const submitting = createMutation.isPending || updateMutation.isPending;
  const categoryValue = form.watch("category");
  const serviceTypeValue = form.watch("service_type");
  const isActiveValue = form.watch("is_active");
  const iconValue = form.watch("icon");
  const idleSubmitLabel = isCreate
    ? t("tags.features.dialog.submit_create")
    : t("common:actions.save");

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults(categories) : editDefaults(props.feature));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.feature.id]);

  const handleSubmit = async (values: FeatureWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("tags.features.toasts.created"));
      } else {
        await updateMutation.mutateAsync(values);
        toast.success(t("tags.features.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("tags.features.dialog.create_title")
              : t("tags.features.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="f-name">{t("tags.features.dialog.fields.name")}</Label>
            <Input id="f-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="f-slug">{t("tags.features.dialog.fields.slug")}</Label>
            <Input id="f-slug" {...form.register("slug")} />
            {form.formState.errors.slug ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.slug.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="f-category">{t("tags.features.dialog.fields.category")}</Label>
              <Select
                value={categoryValue ? String(categoryValue) : ""}
                onValueChange={(v) => form.setValue("category", Number(v))}
              >
                <SelectTrigger
                  id="f-category"
                  aria-label={t("tags.features.dialog.fields.category")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="f-service-type">
                {t("tags.features.dialog.fields.service_type")}
              </Label>
              <Select
                value={serviceTypeValue ?? "amenity"}
                onValueChange={(v) => form.setValue("service_type", v as FeatureServiceType)}
              >
                <SelectTrigger
                  id="f-service-type"
                  aria-label={t("tags.features.dialog.fields.service_type")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FEATURE_SERVICE_TYPES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {t(`tags.features.service_type.${s}` as "tags.features.service_type.amenity")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="f-description">{t("tags.features.dialog.fields.description")}</Label>
            <Textarea id="f-description" rows={3} {...form.register("description")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="f-icon">{t("tags.features.dialog.fields.icon")}</Label>
              <IconPicker
                id="f-icon"
                aria-label={t("tags.features.dialog.fields.icon")}
                value={iconValue ?? ""}
                onChange={(name) => form.setValue("icon", name)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="f-sort">{t("tags.features.dialog.fields.sort_order")}</Label>
              <Input
                id="f-sort"
                type="number"
                min={0}
                {...form.register("sort_order", { valueAsNumber: true })}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="f-active"
              checked={isActiveValue ?? true}
              onCheckedChange={(c) => form.setValue("is_active", Boolean(c))}
            />
            <Label htmlFor="f-active">{t("tags.features.dialog.fields.is_active")}</Label>
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("common:actions.saving") : idleSubmitLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
