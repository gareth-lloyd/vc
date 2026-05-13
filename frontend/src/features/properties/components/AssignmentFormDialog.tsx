import { useEffect, useState } from "react";
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
import type { PropertyId } from "@/lib/query/keys";
import { useCreatePropertyContact, useUpdatePropertyContact } from "../hooks";
import {
  propertyContactAssignmentWriteInputSchema,
  type Contact,
  type PropertyContactAssignment,
  type PropertyContactAssignmentWriteInput,
} from "../schemas";
import { ContactPicker } from "./ContactPicker";

interface CommonProps {
  propertyId: PropertyId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreateNewContact?: () => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  assignment: PropertyContactAssignment;
  contact: Contact;
}

type AssignmentFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: PropertyContactAssignmentWriteInput = {
  contact: 0,
  role: "",
  start_date: "",
  end_date: "",
  is_primary: false,
};

function defaultsFromAssignment(a: PropertyContactAssignment): PropertyContactAssignmentWriteInput {
  return {
    contact: a.contact,
    role: a.role ?? "",
    start_date: a.start_date ?? "",
    end_date: a.end_date ?? "",
    is_primary: a.is_primary ?? false,
  };
}

export function AssignmentFormDialog(props: AssignmentFormDialogProps) {
  const { propertyId, open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<PropertyContactAssignmentWriteInput>({
    resolver: zodResolver(propertyContactAssignmentWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromAssignment(props.assignment),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(
    isCreate ? null : props.contact,
  );

  const createMutation = useCreatePropertyContact(propertyId);
  const updateMutation = useUpdatePropertyContact(propertyId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromAssignment(props.assignment));
      setSelectedContact(isCreate ? null : props.contact);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.assignment.id]);

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
      toast.success(isCreate ? "Contact added" : "Assignment updated");
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error("Something went wrong");
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isCreate ? "Add contact" : "Edit assignment"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          {isCreate ? (
            <div className="space-y-2">
              <Label>Contact</Label>
              <ContactPicker
                value={selectedContact}
                onChange={handleContactSelect}
                onCreateNew={props.onCreateNewContact}
              />
              {form.formState.errors.contact ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.contact.message}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="assignment-role">Role</Label>
            <Input
              id="assignment-role"
              placeholder="e.g. owner, cleaner"
              {...form.register("role")}
            />
            {form.formState.errors.role ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.role.message}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="assignment-start">Start date</Label>
              <Input id="assignment-start" type="date" {...form.register("start_date")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="assignment-end">End date</Label>
              <Input id="assignment-end" type="date" {...form.register("end_date")} />
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox
              checked={!!form.watch("is_primary")}
              onCheckedChange={(v) => form.setValue("is_primary", v === true)}
            />
            <span>Primary contact</span>
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
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Saving…" : isCreate ? "Save contact" : "Update assignment"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
