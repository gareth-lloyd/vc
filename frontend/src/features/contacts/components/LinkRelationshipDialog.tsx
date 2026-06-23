import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { fieldErrorText } from "@/lib/forms/fieldError";
import { ApiError } from "@/lib/api/errors";
import type { ContactId } from "@/lib/query/keys";
import { useCreateContactRelationship } from "../hooks";
import {
  relationshipWriteInputSchema,
  type Contact,
  type RelationshipWriteInput,
} from "../schemas";
import { RELATIONSHIP_KINDS } from "../personRelationships";
import { ContactPicker } from "./ContactPicker";
import { ContactFormDialog } from "./ContactFormDialog";

interface LinkRelationshipDialogProps {
  contactId: ContactId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULTS: RelationshipWriteInput = {
  to_person: 0,
  kind: "",
  note: "",
};

export function LinkRelationshipDialog({
  contactId,
  open,
  onOpenChange,
}: LinkRelationshipDialogProps) {
  const { t } = useTranslation("contacts");
  const form = useForm<RelationshipWriteInput>({
    resolver: zodResolver(relationshipWriteInputSchema),
    defaultValues: DEFAULTS,
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  // The picker emits a Contact OBJECT; the form field `to_person` is its PK.
  // Hold the object for display and mirror its id into RHF on every change.
  const [picked, setPicked] = useState<Contact | null>(null);
  const [createContactOpen, setCreateContactOpen] = useState(false);

  const createMutation = useCreateContactRelationship(contactId);
  const submitting = createMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(DEFAULTS);
      setPicked(null);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const selectContact = (contact: Contact) => {
    setPicked(contact);
    form.setValue("to_person", contact.id, { shouldValidate: true });
  };

  const handleSubmit = async (values: RelationshipWriteInput) => {
    setTopLevelError(null);
    try {
      await createMutation.mutateAsync({
        to_person: values.to_person,
        kind: values.kind,
        note: values.note,
      });
      toast.success(t("toasts.link_added"));
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

  const kind = form.watch("kind");

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("actions.link_contact")}</DialogTitle>
          </DialogHeader>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
            <div className="space-y-2">
              <Label htmlFor="relationship-contact">{t("fields.linked_contact")}</Label>
              <ContactPicker
                value={picked}
                onChange={selectContact}
                // Keep THIS dialog mounted+open and stack the create dialog on
                // top (mirrors ContactFormDialog's own company inline-create).
                // Closing here would unmount the parent-gated dialog and the
                // nested create dialog with it.
                onCreateNew={() => setCreateContactOpen(true)}
              />
              {form.formState.errors.to_person ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.to_person.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="relationship-kind">{t("fields.relationship_kind")}</Label>
              <Select
                value={kind}
                onValueChange={(v) => form.setValue("kind", v, { shouldValidate: true })}
              >
                <SelectTrigger
                  id="relationship-kind"
                  className="w-full"
                  aria-label={t("fields.relationship_kind")}
                >
                  <SelectValue placeholder={t("placeholders.select_relationship_kind")} />
                </SelectTrigger>
                <SelectContent>
                  {RELATIONSHIP_KINDS.map((k) => (
                    <SelectItem key={k.value} value={k.value}>
                      {t(k.labelKey)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {form.formState.errors.kind ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.kind.message)}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="relationship-note">{t("fields.note")}</Label>
              <Input id="relationship-note" {...form.register("note")} />
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
                {submitting ? t("common:actions.saving") : t("common:actions.save")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      {createContactOpen ? (
        <ContactFormDialog
          open={createContactOpen}
          onOpenChange={setCreateContactOpen}
          mode="create"
          // ContactFormDialog closes itself (onOpenChange(false)) after onCreated;
          // we just adopt the new contact. The link dialog stayed open underneath,
          // so its form state (and any chosen kind) survives.
          onCreated={selectContact}
        />
      ) : null}
    </>
  );
}
