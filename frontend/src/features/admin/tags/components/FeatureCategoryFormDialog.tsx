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
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import {
  featureCategoryWriteInputSchema,
  type FeatureCategory,
  type FeatureCategoryWriteInput,
} from "../schemas";
import { useCreateFeatureCategory, useUpdateFeatureCategory } from "../hooks";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { IconPicker } from "@/components/data/IconPicker";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  category: FeatureCategory;
}

type Props = CreateProps | EditProps;

const CREATE_DEFAULTS: FeatureCategoryWriteInput = {
  name: "",
  slug: "",
  description: "",
  icon: "",
  sort_order: 0,
  is_active: true,
};

function editDefaults(c: FeatureCategory): FeatureCategoryWriteInput {
  return {
    name: c.name,
    slug: c.slug,
    description: c.description ?? "",
    icon: c.icon ?? "",
    sort_order: c.sort_order ?? 0,
    is_active: c.is_active,
  };
}

export function FeatureCategoryFormDialog(props: Props) {
  const { open, onOpenChange } = props;
  const isCreate = props.mode === "create";
  const { t } = useTranslation("admin");

  const form = useForm<FeatureCategoryWriteInput>({
    resolver: zodResolver(featureCategoryWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : editDefaults(props.category),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const createMutation = useCreateFeatureCategory();
  const updateMutation = useUpdateFeatureCategory(isCreate ? 0 : props.category.id);
  const submitting = createMutation.isPending || updateMutation.isPending;
  const isActiveValue = form.watch("is_active");
  const iconValue = form.watch("icon");
  const idleSubmitLabel = isCreate
    ? t("tags.categories.dialog.submit_create")
    : t("common:actions.save");

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : editDefaults(props.category));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.category.id]);

  const handleSubmit = async (values: FeatureCategoryWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("tags.categories.toasts.created"));
      } else {
        await updateMutation.mutateAsync(values);
        toast.success(t("tags.categories.toasts.updated"));
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
              ? t("tags.categories.dialog.create_title")
              : t("tags.categories.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="fc-name">{t("tags.categories.dialog.fields.name")}</Label>
            <Input id="fc-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.name.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="fc-slug">{t("tags.categories.dialog.fields.slug")}</Label>
            <Input id="fc-slug" {...form.register("slug")} />
            {form.formState.errors.slug ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.slug.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="fc-description">{t("tags.categories.dialog.fields.description")}</Label>
            <Textarea id="fc-description" rows={3} {...form.register("description")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="fc-icon">{t("tags.categories.dialog.fields.icon")}</Label>
              <IconPicker
                id="fc-icon"
                aria-label={t("tags.categories.dialog.fields.icon")}
                value={iconValue ?? ""}
                onChange={(name) => form.setValue("icon", name)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="fc-sort">{t("tags.categories.dialog.fields.sort_order")}</Label>
              <Input
                id="fc-sort"
                type="number"
                min={0}
                {...form.register("sort_order", { valueAsNumber: true })}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="fc-active"
              checked={isActiveValue ?? true}
              onCheckedChange={(c) => form.setValue("is_active", Boolean(c))}
            />
            <Label htmlFor="fc-active">{t("tags.categories.dialog.fields.is_active")}</Label>
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
