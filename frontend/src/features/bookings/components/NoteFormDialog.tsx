import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import type { BookingId } from "@/lib/query/keys";
import { useCreateBookingNote, useUpdateBookingNote } from "../hooks";
import {
  bookingNoteWriteInputSchema,
  type BookingNote,
  type BookingNoteWriteInput,
} from "../schemas";
import { NoteForm } from "./NoteForm";

interface CommonProps {
  bookingId: BookingId;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  note: BookingNote;
}

type NoteFormDialogProps = CreateProps | EditProps;

const CREATE_DEFAULTS: BookingNoteWriteInput = {
  body: "",
  kind: "general",
  visibility: "staff_only",
  is_pinned: false,
};

function defaultsFromNote(note: BookingNote): BookingNoteWriteInput {
  return {
    body: note.body,
    kind: note.kind,
    visibility: note.visibility,
    is_pinned: note.is_pinned ?? false,
  };
}

export function NoteFormDialog(props: NoteFormDialogProps) {
  const { bookingId, open, onOpenChange } = props;
  const isCreate = props.mode === "create";

  const form = useForm<BookingNoteWriteInput>({
    resolver: zodResolver(bookingNoteWriteInputSchema),
    defaultValues: isCreate ? CREATE_DEFAULTS : defaultsFromNote(props.note),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateBookingNote(bookingId);
  const updateMutation = useUpdateBookingNote(bookingId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? CREATE_DEFAULTS : defaultsFromNote(props.note));
      setTopLevelError(null);
    }
    // form.reset only when (re)opening or when target note changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.note.id]);

  const handleSubmit = async (values: BookingNoteWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
      } else {
        await updateMutation.mutateAsync({ noteId: props.note.id, input: values });
      }
      toast.success("Note saved");
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
          <DialogTitle>{isCreate ? "Add note" : "Edit note"}</DialogTitle>
          <DialogDescription>
            Notes are visible to staff by default; choose another visibility to share with owners or
            guests.
          </DialogDescription>
        </DialogHeader>
        <NoteForm
          form={form}
          onSubmit={handleSubmit}
          topLevelError={topLevelError}
          submitting={submitting}
          submitLabel={isCreate ? "Add note" : "Save"}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
