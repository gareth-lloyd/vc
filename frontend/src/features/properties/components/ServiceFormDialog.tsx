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
import { useCreatePropertyService, useUpdatePropertyService } from "../hooks";
import {
  propertyServiceWriteInputSchema,
  type PropertyService,
  type PropertyServiceWriteInput,
} from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
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
  service: PropertyService;
}

type ServiceFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: PropertyServiceWriteInput = {
  name: "",
  copy: "",
  notes: "",
  applies_from: "",
  applies_to: "",
  is_active: true,
};

function defaultsFromService(service: PropertyService): PropertyServiceWriteInput {
  return {
    name: service.name,
    copy: service.copy,
    notes: service.notes ?? "",
    applies_from: service.applies_from ?? "",
    applies_to: service.applies_to ?? "",
    is_active: service.is_active,
  };
}

export function ServiceFormDialog(props: ServiceFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const { t } = useTranslation("properties");
  const isCreate = props.mode === "create";

  const form = useForm<PropertyServiceWriteInput>({
    resolver: zodResolver(propertyServiceWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromService(props.service),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreatePropertyService(propertyId);
  const updateMutation = useUpdatePropertyService(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromService(props.service));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.service.id]);

  const handleSubmit = async (values: PropertyServiceWriteInput) => {
    setTopLevelError(null);
    // An empty date input is "no band on that end" — send explicit `null`, never
    // the empty string the API rejects as an invalid date, and never `undefined`
    // (which a PATCH would omit, leaving a previously-set band uncleared). `null`
    // both creates an open-ended band and clears one on edit.
    const body: PropertyServiceWriteInput = {
      ...values,
      applies_from: values.applies_from || null,
      applies_to: values.applies_to || null,
    };
    try {
      if (isCreate) {
        await createMutation.mutateAsync(body);
        toast.success(t("services.toasts.created"));
      } else {
        await updateMutation.mutateAsync({ serviceId: props.service.id, input: body });
        toast.success(t("services.toasts.updated"));
      }
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(
          isCreate ? t("services.toasts.create_failed") : t("services.toasts.update_failed"),
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
            {isCreate ? t("services.dialog.create_title") : t("services.dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="service-name">{t("services.dialog.fields.name")}</Label>
            <Input
              id="service-name"
              placeholder={t("services.dialog.fields.name_placeholder")}
              {...form.register("name")}
            />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.name.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="service-copy">{t("services.dialog.fields.copy")}</Label>
            <Textarea
              id="service-copy"
              rows={2}
              placeholder={t("services.dialog.fields.copy_placeholder")}
              {...form.register("copy")}
            />
            {form.formState.errors.copy ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.copy.message)}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="service-notes">{t("services.dialog.fields.notes")}</Label>
            <Textarea id="service-notes" rows={2} {...form.register("notes")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="service-applies-from">
                {t("services.dialog.fields.applies_from")}
              </Label>
              <Input id="service-applies-from" type="date" {...form.register("applies_from")} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="service-applies-to">{t("services.dialog.fields.applies_to")}</Label>
              <Input id="service-applies-to" type="date" {...form.register("applies_to")} />
              {form.formState.errors.applies_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.applies_to.message)}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="service-is-active"
              checked={isActive}
              onCheckedChange={(v) => form.setValue("is_active", v === true)}
            />
            <Label htmlFor="service-is-active">{t("services.dialog.fields.is_active")}</Label>
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              {t("services.dialog.actions.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t("services.dialog.actions.saving") : t("services.dialog.actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
