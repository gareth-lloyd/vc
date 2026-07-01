import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { MoneyInput } from "@/components/ui/money-input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { currencyAdornment } from "@/lib/format/money";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useCreateDiscount, useUpdateDiscount } from "../hooks";
import {
  discountWriteInputSchema,
  type DiscountWriteInput,
  type DiscountWritePayload,
} from "../schemas";
import type { Discount } from "@/features/properties/schemas";

interface CommonProps {
  propertyId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The property's resolved currency, shown as the amount adornment. */
  currencyCode?: string | null;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  entity: Discount;
}

type DiscountFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: DiscountWriteInput = {
  name: "",
  code: "",
  kind: "",
  amount: "",
  min_nights: null,
  threshold_days: null,
  valid_from: "",
  valid_to: "",
  max_uses: null,
  is_active: true,
};

function defaultsFromDiscount(discount: Discount): DiscountWriteInput {
  return {
    name: discount.name,
    code: discount.code ?? "",
    kind: discount.kind ?? discount.rule_kind ?? "",
    amount: discount.amount ?? "",
    min_nights: discount.min_nights ?? null,
    threshold_days: discount.threshold_days ?? null,
    valid_from: discount.valid_from ?? "",
    valid_to: discount.valid_to ?? "",
    max_uses: discount.max_uses ?? null,
    is_active: discount.is_active ?? true,
  };
}

function toPayload(values: DiscountWriteInput): DiscountWritePayload {
  // An empty amount/date is "unset" — send explicit `null`, never the empty
  // string the API rejects, and never `undefined` (which a PATCH omits).
  return {
    ...values,
    amount: values.amount ? values.amount : null,
    valid_from: values.valid_from || null,
    valid_to: values.valid_to || null,
  };
}

/** RHF number field: "" → null, else Number — keeps the zod number|null happy. */
const asNumberOrNull = (v: unknown) => (v === "" || v == null ? null : Number(v));

export function DiscountFormDialog(props: DiscountFormDialogProps) {
  const { propertyId, open, onOpenChange, currencyCode } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";
  const amountAdornment = currencyAdornment(currencyCode);

  const form = useForm<DiscountWriteInput>({
    resolver: zodResolver(discountWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromDiscount(props.entity),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateDiscount(propertyId);
  const updateMutation = useUpdateDiscount(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromDiscount(props.entity));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.entity.id]);

  const handleSubmit = async (values: DiscountWriteInput) => {
    setTopLevelError(null);
    const body = toPayload(values);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(body);
        toast.success(t("rate_workbench.inspector.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ discountId: props.entity.id, input: body });
        toast.success(t("rate_workbench.inspector.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("rate_workbench.inspector.toasts.save_failed"));
      }
    }
  };

  const isActive = form.watch("is_active") ?? true;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("rate_workbench.inspector.discount_dialog.create_title")
              : t("rate_workbench.inspector.discount_dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="discount-name">{t("rate_workbench.inspector.fields.name")}</Label>
            <Input id="discount-name" {...form.register("name")} />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="discount-code">{t("rate_workbench.inspector.fields.code")}</Label>
              <Input id="discount-code" {...form.register("code")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-kind">{t("rate_workbench.inspector.fields.kind")}</Label>
              <Input id="discount-kind" {...form.register("kind")} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="discount-amount">{t("rate_workbench.inspector.fields.amount")}</Label>
              <MoneyInput
                id="discount-amount"
                inputMode="decimal"
                adornment={amountAdornment}
                {...form.register("amount")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-min-nights">
                {t("rate_workbench.inspector.fields.min_nights")}
              </Label>
              <Input
                id="discount-min-nights"
                type="number"
                min={0}
                {...form.register("min_nights", { setValueAs: asNumberOrNull })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-max-uses">
                {t("rate_workbench.inspector.fields.max_uses")}
              </Label>
              <Input
                id="discount-max-uses"
                type="number"
                min={0}
                {...form.register("max_uses", { setValueAs: asNumberOrNull })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="discount-valid-from">
                {t("rate_workbench.inspector.fields.valid_from")}
              </Label>
              <Input id="discount-valid-from" type="date" {...form.register("valid_from")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="discount-valid-to">
                {t("rate_workbench.inspector.fields.valid_to")}
              </Label>
              <Input id="discount-valid-to" type="date" {...form.register("valid_to")} />
              {form.formState.errors.valid_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.valid_to.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="discount-is-active"
              checked={isActive}
              onCheckedChange={(v) => form.setValue("is_active", v === true)}
            />
            <Label htmlFor="discount-is-active">
              {t("rate_workbench.inspector.fields.is_active")}
            </Label>
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("rate_workbench.inspector.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("rate_workbench.inspector.actions.saving")
                : t("rate_workbench.inspector.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
