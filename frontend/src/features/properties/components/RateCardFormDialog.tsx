import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { useCreateRateCard, useUpdateRateCard } from "../hooks";
import { rateCardWriteInputSchema, type RateCard, type RateCardWriteInput } from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  seasonId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  card: RateCard;
}

type RateCardFormDialogProps = CreateProps | EditProps;

function createDefaults(): RateCardWriteInput {
  return {
    name: "",
    description: "",
    min_nights: 1,
    max_nights: null,
    is_active: true,
    notes: "",
  };
}

function defaultsFromCard(card: RateCard): RateCardWriteInput {
  return {
    name: card.name,
    description: card.description ?? "",
    min_nights: card.min_nights ?? 1,
    max_nights: card.max_nights ?? null,
    is_active: card.is_active ?? true,
    notes: card.notes ?? "",
  };
}

export function RateCardFormDialog(props: RateCardFormDialogProps) {
  const { seasonId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const form = useForm<RateCardWriteInput>({
    resolver: zodResolver(rateCardWriteInputSchema),
    defaultValues: isCreate ? createDefaults() : defaultsFromCard(props.card),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateRateCard(seasonId);
  const updateMutation = useUpdateRateCard(seasonId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults() : defaultsFromCard(props.card));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.card.id]);

  const handleSubmit = async (values: RateCardWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
        toast.success(t("pricing.rate_card.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ cardId: props.card.id, input: values });
        toast.success(t("pricing.rate_card.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(
          isCreate
            ? t("pricing.rate_card.toasts.create_failed")
            : t("pricing.rate_card.toasts.update_failed"),
        );
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
              ? t("pricing.rate_card.dialog.create_title")
              : t("pricing.rate_card.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="rate-card-name">{t("pricing.rate_card.dialog.fields.name")}</Label>
            <Input
              id="rate-card-name"
              placeholder={t("pricing.rate_card.dialog.fields.name_placeholder")}
              {...form.register("name")}
            />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="rate-card-description">
              {t("pricing.rate_card.dialog.fields.description")}
            </Label>
            <Textarea id="rate-card-description" rows={2} {...form.register("description")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="rate-card-min-nights">
                {t("pricing.rate_card.dialog.fields.min_nights")}
              </Label>
              <Input
                id="rate-card-min-nights"
                type="number"
                min={1}
                {...form.register("min_nights", {
                  setValueAs: (v) => (v === "" || v == null ? undefined : Number(v)),
                })}
              />
              {form.formState.errors.min_nights ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.min_nights.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rate-card-max-nights">
                {t("pricing.rate_card.dialog.fields.max_nights")}
              </Label>
              <Input
                id="rate-card-max-nights"
                type="number"
                min={1}
                {...form.register("max_nights", {
                  setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
                })}
              />
              {form.formState.errors.max_nights ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.max_nights.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="rate-card-is-active"
              checked={isActive}
              onCheckedChange={(v) => form.setValue("is_active", v === true)}
            />
            <Label htmlFor="rate-card-is-active">
              {t("pricing.rate_card.dialog.fields.is_active")}
            </Label>
          </div>

          <div className="space-y-2">
            <Label htmlFor="rate-card-notes">{t("pricing.rate_card.dialog.fields.notes")}</Label>
            <Textarea id="rate-card-notes" rows={2} {...form.register("notes")} />
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("pricing.rate_card.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? t("pricing.rate_card.dialog.actions.saving")
                : t("pricing.rate_card.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
