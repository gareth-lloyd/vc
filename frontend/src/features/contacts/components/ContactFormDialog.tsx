import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import type { ContactId } from "@/lib/query/keys";
import { useCreateContact, useUpdateContact } from "../hooks";
import {
  contactCreateInputSchema,
  contactWriteInputSchema,
  type Contact,
  type ContactCreateBody,
  type ContactCreateInput,
} from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

interface CommonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
  onCreated?: (contact: Contact) => void;
}

interface EditProps extends CommonProps {
  mode: "edit";
  contactId: ContactId;
  contact: Contact;
}

type ContactFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: ContactCreateInput = {
  title: "",
  first_name: "",
  last_name: "",
  company: "",
  website_url: "",
  preferred_method: "",
  address_line_1: "",
  address_line_2: "",
  notes: "",
  email: "",
  phone: "",
};

function defaultsFromContact(c: Contact): ContactCreateInput {
  return {
    title: c.title ?? "",
    first_name: c.first_name ?? "",
    last_name: c.last_name ?? "",
    company: c.company ?? "",
    website_url: c.website_url ?? "",
    preferred_method: c.preferred_method ?? "",
    address_line_1: c.address_line_1 ?? "",
    address_line_2: c.address_line_2 ?? "",
    notes: c.notes ?? "",
    // Channels are edited through the dedicated email/phone dialogs, not here.
    email: "",
    phone: "",
  };
}

export function ContactFormDialog(props: ContactFormDialogProps) {
  const { t } = useTranslation("contacts");
  const { open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  // Create validates the at-least-one-channel rule (contactCreateInputSchema);
  // edit reuses the base schema (channels are managed via their own dialogs).
  const resolver = (
    isCreate ? zodResolver(contactCreateInputSchema) : zodResolver(contactWriteInputSchema)
  ) as Resolver<ContactCreateInput>;

  const form = useForm<ContactCreateInput>({
    resolver,
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromContact(props.contact),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateContact();
  const updateMutation = useUpdateContact(isCreate ? 0 : props.contactId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromContact(props.contact));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.contactId]);

  const handleSubmit = async (values: ContactCreateInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        const { email, phone, ...details } = values;
        const body: ContactCreateBody = {
          ...details,
          emails: email ? [{ email, is_primary: true }] : undefined,
          phones: phone ? [{ number: phone, is_primary: true }] : undefined,
        };
        const created = await createMutation.mutateAsync(body);
        toast.success(t("toasts.created"));
        props.onCreated?.(created);
      } else {
        const { email: _email, phone: _phone, ...details } = values;
        void _email;
        void _phone;
        await updateMutation.mutateAsync(details);
        toast.success(t("toasts.updated"));
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
            {isCreate ? t("headings.create_dialog") : t("headings.edit_dialog")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label htmlFor="contact-title">{t("fields.title")}</Label>
              <Input
                id="contact-title"
                placeholder={t("placeholders.title")}
                {...form.register("title")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact-first-name">{t("fields.first_name")}</Label>
              <Input id="contact-first-name" {...form.register("first_name")} />
              {form.formState.errors.first_name ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.first_name.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact-last-name">{t("fields.last_name")}</Label>
              <Input id="contact-last-name" {...form.register("last_name")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="contact-company">{t("fields.company")}</Label>
            <Input id="contact-company" {...form.register("company")} />
          </div>

          {isCreate ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="contact-email">{t("fields.email")}</Label>
                <Input
                  id="contact-email"
                  type="email"
                  placeholder={t("placeholders.email")}
                  {...form.register("email")}
                />
                {form.formState.errors.email ? (
                  <p className="text-destructive text-sm" role="alert">
                    {form.formState.errors.email.message}
                  </p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="contact-phone">{t("fields.phone")}</Label>
                <Input
                  id="contact-phone"
                  placeholder={t("placeholders.phone")}
                  {...form.register("phone")}
                />
              </div>
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="contact-website">{t("fields.website")}</Label>
              <Input id="contact-website" {...form.register("website_url")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact-preferred-method">
                {t("fields.preferred_contact_method")}
              </Label>
              <Input
                id="contact-preferred-method"
                placeholder={t("placeholders.preferred_method")}
                {...form.register("preferred_method")}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="contact-address-1">{t("fields.address_line_1")}</Label>
            <Input id="contact-address-1" {...form.register("address_line_1")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="contact-address-2">{t("fields.address_line_2")}</Label>
            <Input id="contact-address-2" {...form.register("address_line_2")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="contact-notes">{t("fields.notes")}</Label>
            <Textarea id="contact-notes" rows={3} {...form.register("notes")} />
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
              {submitting
                ? t("common:actions.saving")
                : isCreate
                  ? t("actions.create")
                  : t("common:actions.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
