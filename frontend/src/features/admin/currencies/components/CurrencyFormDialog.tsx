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
import { currencyWriteInputSchema, type Currency, type CurrencyWriteInput } from "../schemas";
import { useCreateCurrency, useUpdateCurrency } from "../hooks";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  currency: Currency;
}

type Props = CreateProps | EditProps;

const CREATE_DEFAULTS: CurrencyWriteInput = {
  code: "",
  name: "",
  symbol: "",
  decimal_places: 2,
  is_active: true,
};

function editDefaults(c: Currency): CurrencyWriteInput {
  return {
    code: c.code,
    name: c.name,
    symbol: c.symbol ?? "",
    decimal_places: c.decimal_places ?? 2,
    is_active: c.is_active,
  };
}

export function CurrencyFormDialog(props: Props) {
  const { open, onOpenChange } = props;
  const isCreate = props.mode === "create";
  const { t } = useTranslation("admin");

  const form = useForm<CurrencyWriteInput>({
    resolver: zodResolver(currencyWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : editDefaults(props.currency),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const createMutation = useCreateCurrency();
  const updateMutation = useUpdateCurrency(isCreate ? "" : props.currency.code);
  const submitting = createMutation.isPending || updateMutation.isPending;
  const isActiveValue = form.watch("is_active");
  const idleSubmitLabel = isCreate
    ? t("currencies.dialog.submit_create")
    : t("common:actions.save");

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : editDefaults(props.currency));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.currency.code]);

  const handleSubmit = async (values: CurrencyWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("currencies.toasts.created"));
      } else {
        await updateMutation.mutateAsync(values);
        toast.success(t("currencies.toasts.updated"));
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
            {isCreate ? t("currencies.dialog.create_title") : t("currencies.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="currency-code">{t("currencies.dialog.fields.code")}</Label>
              <Input
                id="currency-code"
                {...form.register("code")}
                disabled={!isCreate}
                maxLength={3}
              />
              {form.formState.errors.code ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.code.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="currency-symbol">{t("currencies.dialog.fields.symbol")}</Label>
              <Input id="currency-symbol" {...form.register("symbol")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="currency-name">{t("currencies.dialog.fields.name")}</Label>
            <Input id="currency-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.name.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="currency-decimals">
              {t("currencies.dialog.fields.decimal_places")}
            </Label>
            <Input
              id="currency-decimals"
              type="number"
              min={0}
              max={8}
              {...form.register("decimal_places", { valueAsNumber: true })}
            />
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="currency-active"
              checked={isActiveValue ?? true}
              onCheckedChange={(c) => form.setValue("is_active", Boolean(c))}
            />
            <Label htmlFor="currency-active">{t("currencies.dialog.fields.is_active")}</Label>
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
