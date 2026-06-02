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
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { countryWriteInputSchema, type Country, type CountryWriteInput } from "../schemas";
import { useCreateCountry, useUpdateCountry } from "../hooks";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  country: Country;
}

type Props = CreateProps | EditProps;

const CREATE_DEFAULTS: CountryWriteInput = {
  iso2: "",
  name: "",
  iso3: "",
  dial_code: "",
  default_tax_rate: "",
  sort_order: 0,
  is_active: true,
};

function editDefaults(c: Country): CountryWriteInput {
  return {
    iso2: c.iso2,
    name: c.name,
    iso3: c.iso3 ?? "",
    dial_code: c.dial_code ?? "",
    default_tax_rate: c.default_tax_rate == null ? "" : String(c.default_tax_rate),
    sort_order: c.sort_order ?? 0,
    is_active: c.is_active,
  };
}

export function CountryFormDialog(props: Props) {
  const { open, onOpenChange } = props;
  const isCreate = props.mode === "create";
  const { t } = useTranslation("admin");

  const form = useForm<CountryWriteInput>({
    resolver: zodResolver(countryWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : editDefaults(props.country),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const createMutation = useCreateCountry();
  const updateMutation = useUpdateCountry(isCreate ? "" : props.country.iso2);
  const submitting = createMutation.isPending || updateMutation.isPending;
  const isActiveValue = form.watch("is_active");
  const idleSubmitLabel = isCreate ? t("countries.dialog.submit_create") : t("common:actions.save");

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : editDefaults(props.country));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.country.iso2]);

  const handleSubmit = async (values: CountryWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("countries.toasts.created"));
      } else {
        await updateMutation.mutateAsync(values);
        toast.success(t("countries.toasts.updated"));
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
            {isCreate ? t("countries.dialog.create_title") : t("countries.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="country-iso2">{t("countries.dialog.fields.iso2")}</Label>
              <Input
                id="country-iso2"
                {...form.register("iso2")}
                disabled={!isCreate}
                maxLength={2}
              />
              {form.formState.errors.iso2 ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.iso2.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="country-iso3">{t("countries.dialog.fields.iso3")}</Label>
              <Input id="country-iso3" {...form.register("iso3")} maxLength={3} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="country-name">{t("countries.dialog.fields.name")}</Label>
            <Input id="country-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.name.message}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="country-dial">{t("countries.dialog.fields.dial_code")}</Label>
              <Input id="country-dial" {...form.register("dial_code")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="country-tax">{t("countries.dialog.fields.default_tax_rate")}</Label>
              <Input id="country-tax" {...form.register("default_tax_rate")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="country-sort">{t("countries.dialog.fields.sort_order")}</Label>
              <Input
                id="country-sort"
                type="number"
                min={0}
                {...form.register("sort_order", { valueAsNumber: true })}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="country-active"
              checked={isActiveValue ?? true}
              onCheckedChange={(c) => form.setValue("is_active", Boolean(c))}
            />
            <Label htmlFor="country-active">{t("countries.dialog.fields.is_active")}</Label>
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
