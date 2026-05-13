import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import type { ContactId } from "@/lib/query/keys";
import { useCreateContactPhone, useUpdateContactPhone } from "../hooks";
import {
  contactPhoneWriteInputSchema,
  type ContactPhone,
  type ContactPhoneWriteInput,
} from "../schemas";

interface CommonProps {
  contactId: ContactId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  phone: ContactPhone;
}

type PhoneFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: ContactPhoneWriteInput = {
  number: "",
  label: "",
  is_primary: false,
};

function defaultsFromPhone(p: ContactPhone): ContactPhoneWriteInput {
  return {
    number: p.number,
    label: p.label ?? "",
    is_primary: p.is_primary ?? false,
  };
}

export function PhoneFormDialog(props: PhoneFormDialogProps) {
  const { t } = useTranslation("contacts");
  const { contactId, open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<ContactPhoneWriteInput>({
    resolver: zodResolver(contactPhoneWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromPhone(props.phone),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateContactPhone(contactId);
  const updateMutation = useUpdateContactPhone(contactId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromPhone(props.phone));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.phone.id]);

  const handleSubmit = async (values: ContactPhoneWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
      } else {
        await updateMutation.mutateAsync({ phoneId: props.phone.id, input: values });
      }
      toast.success(isCreate ? t("toasts.phone_added") : t("toasts.phone_updated"));
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

  let submitLabel: string;
  if (submitting) submitLabel = t("common:actions.saving");
  else if (isCreate) submitLabel = t("actions.add_phone");
  else submitLabel = t("common:actions.save");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("headings.add_phone_dialog") : t("headings.edit_phone_dialog")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="contact-phone">{t("fields.phone_number")}</Label>
            <Input
              id="contact-phone"
              type="tel"
              placeholder={t("placeholders.phone")}
              autoFocus
              {...form.register("number")}
              aria-invalid={!!form.formState.errors.number}
            />
            {form.formState.errors.number ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.number.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="phone-label">{t("fields.label")}</Label>
            <Input
              id="phone-label"
              placeholder={t("placeholders.phone_label")}
              {...form.register("label")}
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={!!form.watch("is_primary")}
              onCheckedChange={(v) => form.setValue("is_primary", v === true)}
            />
            <span>{t("checkboxes.primary_phone")}</span>
          </label>

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
              {submitLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
