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
import { useCreateContactEmail, useUpdateContactEmail } from "../hooks";
import {
  contactEmailWriteInputSchema,
  type ContactEmail,
  type ContactEmailWriteInput,
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
  email: ContactEmail;
}

type EmailFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: ContactEmailWriteInput = {
  email: "",
  label: "",
  is_primary: false,
};

function defaultsFromEmail(e: ContactEmail): ContactEmailWriteInput {
  return {
    email: e.email,
    label: e.label ?? "",
    is_primary: e.is_primary ?? false,
  };
}

export function EmailFormDialog(props: EmailFormDialogProps) {
  const { t } = useTranslation("contacts");
  const { contactId, open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<ContactEmailWriteInput>({
    resolver: zodResolver(contactEmailWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromEmail(props.email),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateContactEmail(contactId);
  const updateMutation = useUpdateContactEmail(contactId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromEmail(props.email));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.email.id]);

  const handleSubmit = async (values: ContactEmailWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
      } else {
        await updateMutation.mutateAsync({ emailId: props.email.id, input: values });
      }
      toast.success(isCreate ? t("toasts.email_added") : t("toasts.email_updated"));
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
  else if (isCreate) submitLabel = t("actions.add_email");
  else submitLabel = t("common:actions.save");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate ? t("headings.add_email_dialog") : t("headings.edit_email_dialog")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="contact-email">{t("fields.email")}</Label>
            <Input
              id="contact-email"
              type="email"
              placeholder={t("placeholders.email")}
              autoFocus
              {...form.register("email")}
              aria-invalid={!!form.formState.errors.email}
            />
            {form.formState.errors.email ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.email.message}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="email-label">{t("fields.label")}</Label>
            <Input
              id="email-label"
              placeholder={t("placeholders.email_label")}
              {...form.register("label")}
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={!!form.watch("is_primary")}
              onCheckedChange={(v) => form.setValue("is_primary", v === true)}
            />
            <span>{t("checkboxes.primary_email")}</span>
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
