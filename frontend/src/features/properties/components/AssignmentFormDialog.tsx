import { useEffect, useState } from "react";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { useTranslation } from "react-i18next";
import { useController, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import type { PropertyId } from "@/lib/query/keys";
import { useCreatePropertyContact, useUpdatePropertyContact } from "../hooks";
import {
  PROPERTY_CONTACT_ROLES,
  propertyContactAssignmentWriteInputSchema,
  type PropertyContactAssignment,
  type PropertyContactAssignmentWriteInput,
  type PropertyContactRole,
} from "../schemas";
import type { Contact } from "@/features/contacts/schemas";
import { ContactPicker } from "@/features/contacts/components/ContactPicker";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { fieldErrorText } from "@/lib/forms/fieldError";

interface CommonProps {
  propertyId: PropertyId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreateNewContact?: () => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
  /** Pre-select this contact (GAP-027): a contact just created inline lands
   * selected in the picker instead of forcing the user to re-find it. */
  initialContact?: Contact | null;
}

interface EditProps extends CommonProps {
  mode: "edit";
  assignment: PropertyContactAssignment;
  contact: Contact;
}

type AssignmentFormDialogProps = CreateProps | EditProps;

// The role <Select> starts unset (showing a placeholder) so the user must make
// an explicit choice; the empty string fails the required-enum validation.
const UNSET_ROLE = "" as PropertyContactRole;

function asRole(value: string | null | undefined): PropertyContactRole {
  return PROPERTY_CONTACT_ROLES.includes(value as PropertyContactRole)
    ? (value as PropertyContactRole)
    : UNSET_ROLE;
}

const CREATE_DEFAULTS: PropertyContactAssignmentWriteInput = {
  contact: 0,
  role: UNSET_ROLE,
  start_date: "",
  end_date: "",
  is_primary: false,
};

function createDefaults(initialContact?: Contact | null): PropertyContactAssignmentWriteInput {
  return { ...CREATE_DEFAULTS, contact: initialContact?.id ?? 0 };
}

function defaultsFromAssignment(a: PropertyContactAssignment): PropertyContactAssignmentWriteInput {
  return {
    // This dialog is Person-only and is never opened for an org-assignee row
    // (PeopleTab gates it on a loaded contact); fall back to 0 to satisfy the
    // contact-required write schema if it ever is.
    contact: a.contact ?? 0,
    role: asRole(a.role),
    start_date: a.start_date ?? "",
    end_date: a.end_date ?? "",
    is_primary: a.is_primary ?? false,
  };
}

export function AssignmentFormDialog(props: AssignmentFormDialogProps) {
  const { t } = useTranslation("properties");
  const { propertyId, open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<PropertyContactAssignmentWriteInput>({
    resolver: zodResolver(propertyContactAssignmentWriteInputSchema),
    defaultValues: isCreate
      ? createDefaults(props.initialContact)
      : defaultsFromAssignment(props.assignment),
  });
  const roleCtrl = useController({ control: form.control, name: "role" });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(
    isCreate ? (props.initialContact ?? null) : props.contact,
  );

  const createMutation = useCreatePropertyContact(propertyId);
  const updateMutation = useUpdatePropertyContact(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(
        isCreate ? createDefaults(props.initialContact) : defaultsFromAssignment(props.assignment),
      );
      setSelectedContact(isCreate ? (props.initialContact ?? null) : props.contact);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? props.initialContact?.id : props.assignment.id]);

  const handleContactSelect = (contact: Contact) => {
    setSelectedContact(contact);
    form.setValue("contact", contact.id);
  };

  const handleSubmit = async (values: PropertyContactAssignmentWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
      } else {
        const { role, start_date, end_date, is_primary } = values;
        await updateMutation.mutateAsync({
          mappingId: props.assignment.id,
          input: { role, start_date, end_date, is_primary },
        });
      }
      toast.success(
        isCreate ? t("people.toasts.contact_added") : t("people.toasts.assignment_updated"),
      );
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
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isCreate
              ? t("people.assignment_dialog.create_title")
              : t("people.assignment_dialog.edit_title")}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          {isCreate ? (
            <div className="space-y-2">
              <Label>{t("people.assignment_dialog.contact_label")}</Label>
              <ContactPicker
                value={selectedContact}
                onChange={handleContactSelect}
                onCreateNew={props.onCreateNewContact}
              />
              {form.formState.errors.contact ? (
                <p className="text-destructive text-sm" role="alert">
                  {fieldErrorText(t, form.formState.errors.contact.message)}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="assignment-role">{t("people.assignment_dialog.role_label")}</Label>
            <Select
              value={roleCtrl.field.value || undefined}
              onValueChange={roleCtrl.field.onChange}
            >
              <SelectTrigger
                id="assignment-role"
                aria-label={t("people.assignment_dialog.role_label")}
              >
                <SelectValue placeholder={t("people.assignment_dialog.role_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                {PROPERTY_CONTACT_ROLES.map((role) => (
                  <SelectItem key={role} value={role}>
                    {t(`people.assignment_dialog.roles.${role}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.role ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldErrorText(t, form.formState.errors.role.message)}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="assignment-start">{t("people.assignment_dialog.start_label")}</Label>
              <Input id="assignment-start" type="date" {...form.register("start_date")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="assignment-end">{t("people.assignment_dialog.end_label")}</Label>
              <Input id="assignment-end" type="date" {...form.register("end_date")} />
            </div>
          </div>

          <CheckboxLabel>
            <Checkbox
              checked={!!form.watch("is_primary")}
              onCheckedChange={(v) => form.setValue("is_primary", v === true)}
            />
            <span>{t("people.assignment_dialog.primary_label")}</span>
          </CheckboxLabel>

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
                  ? t("people.assignment_dialog.save_create")
                  : t("people.assignment_dialog.save_edit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
