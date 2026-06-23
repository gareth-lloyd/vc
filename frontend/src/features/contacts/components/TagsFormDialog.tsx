import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import type { ContactId } from "@/lib/query/keys";
import { useUpdateContact } from "../hooks";
import { PERSON_TAGS } from "../personTags";

interface TagsFormDialogProps {
  contactId: ContactId;
  tags: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface TagsForm {
  tags: string[];
}

export function TagsFormDialog({ contactId, tags, open, onOpenChange }: TagsFormDialogProps) {
  const { t } = useTranslation("contacts");

  // Held in an RHF form so a `field_errors.tags` 4xx surfaces inline; the form's
  // only field is `tags`, the full set the PATCH replaces.
  const form = useForm<TagsForm>({ defaultValues: { tags } });
  const [selected, setSelected] = useState<string[]>(tags);
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const updateMutation = useUpdateContact(contactId);
  const submitting = updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset({ tags });
      setSelected(tags);
      setTopLevelError(null);
    }
    // `contactId` is in the deps so the form re-seeds if the same mounted dialog
    // is ever pointed at a different contact (today the parent open-gates the
    // mount, but don't rely on that). `tags.join(",")` tracks content, not ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, contactId, tags.join(",")]);

  const toggle = (value: string, checked: boolean) => {
    setSelected((prev) => (checked ? [...prev, value] : prev.filter((v) => v !== value)));
  };

  const handleSubmit = async () => {
    setTopLevelError(null);
    form.setValue("tags", selected);
    try {
      await updateMutation.mutateAsync({ tags: selected });
      toast.success(t("toasts.tags_updated"));
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
          <DialogTitle>{t("headings.edit_tags_dialog")}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSubmit();
          }}
          className="space-y-4"
          noValidate
        >
          <div className="space-y-2">
            {PERSON_TAGS.map((tag) => (
              <CheckboxLabel key={tag.value}>
                <Checkbox
                  checked={selected.includes(tag.value)}
                  onCheckedChange={(v) => toggle(tag.value, v === true)}
                />
                <span>{t(tag.labelKey)}</span>
              </CheckboxLabel>
            ))}
          </div>

          {form.formState.errors.tags ? (
            <p className="text-destructive text-sm" role="alert">
              {form.formState.errors.tags.message}
            </p>
          ) : null}

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
  );
}
