import { useController, type UseFormReturn } from "react-hook-form";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  bookingNoteKindOptions,
  bookingNoteVisibilityOptions,
  type BookingNoteWriteInput,
} from "../schemas";

interface NoteFormProps {
  form: UseFormReturn<BookingNoteWriteInput>;
  onSubmit: (values: BookingNoteWriteInput) => void | Promise<void>;
  topLevelError: string | null;
  submitting: boolean;
  submitLabel: string;
  onCancel: () => void;
}

export function NoteForm({
  form,
  onSubmit,
  topLevelError,
  submitting,
  submitLabel,
  onCancel,
}: NoteFormProps) {
  const { t } = useTranslation("bookings");
  const kindCtrl = useController({ control: form.control, name: "kind" });
  const visibilityCtrl = useController({ control: form.control, name: "visibility" });
  const pinnedCtrl = useController({ control: form.control, name: "is_pinned" });

  const kindOptions = bookingNoteKindOptions();
  const visibilityOptions = bookingNoteVisibilityOptions();

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <div className="space-y-2">
        <Label htmlFor="note-body">{t("notes.form.body")}</Label>
        <Textarea
          id="note-body"
          rows={5}
          autoFocus
          {...form.register("body")}
          aria-invalid={!!form.formState.errors.body}
        />
        {form.formState.errors.body ? (
          <p className="text-destructive text-sm" role="alert">
            {form.formState.errors.body.message}
          </p>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="note-kind">{t("notes.form.kind")}</Label>
          <Select value={kindCtrl.field.value} onValueChange={kindCtrl.field.onChange}>
            <SelectTrigger id="note-kind" aria-label={t("notes.form.kind")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {kindOptions.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="note-visibility">{t("notes.form.visibility")}</Label>
          <Select value={visibilityCtrl.field.value} onValueChange={visibilityCtrl.field.onChange}>
            <SelectTrigger id="note-visibility" aria-label={t("notes.form.visibility")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {visibilityOptions.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <Checkbox
          checked={!!pinnedCtrl.field.value}
          onCheckedChange={(v) => pinnedCtrl.field.onChange(v === true)}
        />
        <span>{t("notes.form.pin")}</span>
      </label>

      <FormErrorAlert message={topLevelError} />

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          {t("common:actions.cancel")}
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? t("common:actions.saving") : submitLabel}
        </Button>
      </div>
    </form>
  );
}
