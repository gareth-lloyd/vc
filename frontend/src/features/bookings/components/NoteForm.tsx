import { useController, type UseFormReturn } from "react-hook-form";
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
  BOOKING_NOTE_KIND_OPTIONS,
  BOOKING_NOTE_VISIBILITY_OPTIONS,
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
  const kindCtrl = useController({ control: form.control, name: "kind" });
  const visibilityCtrl = useController({ control: form.control, name: "visibility" });
  const pinnedCtrl = useController({ control: form.control, name: "is_pinned" });

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <div className="space-y-2">
        <Label htmlFor="note-body">Body</Label>
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
          <Label htmlFor="note-kind">Kind</Label>
          <Select value={kindCtrl.field.value} onValueChange={kindCtrl.field.onChange}>
            <SelectTrigger id="note-kind" aria-label="Kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BOOKING_NOTE_KIND_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="note-visibility">Visibility</Label>
          <Select value={visibilityCtrl.field.value} onValueChange={visibilityCtrl.field.onChange}>
            <SelectTrigger id="note-visibility" aria-label="Visibility">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BOOKING_NOTE_VISIBILITY_OPTIONS.map((o) => (
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
        <span>Pin this note</span>
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
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
