import { useEffect, useState } from "react";
import { useController, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { slugify } from "@/lib/format/slug";
import { propertyDetailsPath } from "@/lib/routes";
import { useCreateProperty, usePropertyCategories } from "../hooks";
import { useRegions } from "@/features/availability/hooks";
import { propertyCreateInputSchema, type PropertyCreateInput } from "../schemas";

interface CreatePropertyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const CREATE_DEFAULTS: PropertyCreateInput = {
  name: "",
  display_name: "",
  slug: "",
  // `0` is the unselected sentinel — the schema's `.min(1)` rejects it.
  category: 0,
  region: 0,
};

export function CreatePropertyDialog({ open, onOpenChange }: CreatePropertyDialogProps) {
  const { t } = useTranslation("properties");
  const navigate = useNavigate();

  const form = useForm<PropertyCreateInput>({
    resolver: zodResolver(propertyCreateInputSchema),
    defaultValues: CREATE_DEFAULTS,
  });
  const categoryCtrl = useController({ control: form.control, name: "category" });
  const regionCtrl = useController({ control: form.control, name: "region" });

  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  // Once the operator hand-edits the slug / display name, stop auto-deriving
  // them from the villa name so we never clobber a deliberate value.
  const [slugEdited, setSlugEdited] = useState(false);
  const [displayNameEdited, setDisplayNameEdited] = useState(false);

  const categories = usePropertyCategories();
  const regions = useRegions();
  const createMutation = useCreateProperty();

  useEffect(() => {
    if (open) {
      form.reset(CREATE_DEFAULTS);
      setTopLevelError(null);
      setSlugEdited(false);
      setDisplayNameEdited(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const nameField = form.register("name");
  const slugField = form.register("slug");
  const displayNameField = form.register("display_name");

  const handleNameChange = (value: string) => {
    if (!slugEdited) form.setValue("slug", slugify(value));
    if (!displayNameEdited) form.setValue("display_name", value);
  };

  const handleSubmit = async (values: PropertyCreateInput) => {
    setTopLevelError(null);
    try {
      const created = await createMutation.mutateAsync(values);
      toast.success(t("create.toasts.created"));
      onOpenChange(false);
      // Land the operator on the new villa's edit tabs to keep filling it in.
      navigate(propertyDetailsPath(created.id));
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("common:errors.generic"));
      }
    }
  };

  const categoryOptions = categories.data?.results ?? [];
  const regionOptions = regions.data?.results ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("create.title")}</DialogTitle>
          <DialogDescription>{t("create.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="create-name">{t("create.fields.name")}</Label>
            <Input
              id="create-name"
              {...nameField}
              onChange={(e) => {
                nameField.onChange(e);
                handleNameChange(e.target.value);
              }}
            />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-display-name">{t("create.fields.display_name")}</Label>
            <Input
              id="create-display-name"
              {...displayNameField}
              onChange={(e) => {
                displayNameField.onChange(e);
                setDisplayNameEdited(true);
              }}
            />
            {form.formState.errors.display_name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.display_name.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-slug">{t("create.fields.slug")}</Label>
            <Input
              id="create-slug"
              {...slugField}
              onChange={(e) => {
                slugField.onChange(e);
                setSlugEdited(true);
              }}
            />
            <p className="text-muted-foreground text-xs">{t("create.fields.slug_help")}</p>
            {form.formState.errors.slug ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.slug.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-category">{t("create.fields.category")}</Label>
            <Select
              value={categoryCtrl.field.value ? String(categoryCtrl.field.value) : ""}
              onValueChange={(v) => categoryCtrl.field.onChange(Number(v))}
            >
              <SelectTrigger id="create-category" aria-label={t("create.fields.category")}>
                <SelectValue placeholder={t("create.fields.category_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                {categoryOptions.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.category ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.category.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="create-region">{t("create.fields.region")}</Label>
            <Select
              value={regionCtrl.field.value ? String(regionCtrl.field.value) : ""}
              onValueChange={(v) => regionCtrl.field.onChange(Number(v))}
            >
              <SelectTrigger id="create-region" aria-label={t("create.fields.region")}>
                <SelectValue placeholder={t("create.fields.region_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                {regionOptions.map((r) => (
                  <SelectItem key={r.id} value={String(r.id)}>
                    {r.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.region ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.region.message)}
              </p>
            ) : null}
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {t("create.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
