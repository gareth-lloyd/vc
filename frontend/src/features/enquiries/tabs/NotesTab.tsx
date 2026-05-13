import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { useController } from "react-hook-form";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { formatDate } from "@/lib/format/date";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useCreateEnquiryNote, useEnquiryNotes } from "../hooks";
import {
  ENQUIRY_NOTE_KIND_LABELS,
  ENQUIRY_NOTE_KIND_OPTIONS,
  type EnquiryNote,
  type EnquiryNoteKind,
  enquiryNoteKindSchema,
  enquiryNoteWriteInputSchema,
  type EnquiryNoteWriteInput,
} from "../schemas";
import type { EnquiryOutletContext } from "../EnquiryDetailLayout";

const ALL_VALUE = "__all__";
const KIND_OPTIONS = [{ value: ALL_VALUE, label: "All kinds" }, ...ENQUIRY_NOTE_KIND_OPTIONS];

function sortPinnedFirst(notes: readonly EnquiryNote[]): EnquiryNote[] {
  return [...notes].sort((a, b) => {
    const ap = a.is_pinned ? 0 : 1;
    const bp = b.is_pinned ? 0 : 1;
    if (ap !== bp) return ap - bp;
    return (a.created_at ?? "").localeCompare(b.created_at ?? "");
  });
}

const CREATE_DEFAULTS: EnquiryNoteWriteInput = {
  body: "",
  kind: "general",
  is_pinned: false,
};

interface NoteFormDialogProps {
  enquiryId: number | string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function NoteFormDialog({ enquiryId, open, onOpenChange }: NoteFormDialogProps) {
  const form = useForm<EnquiryNoteWriteInput>({
    resolver: zodResolver(enquiryNoteWriteInputSchema),
    defaultValues: CREATE_DEFAULTS,
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const createMutation = useCreateEnquiryNote(enquiryId);
  const kindCtrl = useController({ control: form.control, name: "kind" });
  const pinnedCtrl = useController({ control: form.control, name: "is_pinned" });

  useEffect(() => {
    if (open) {
      form.reset(CREATE_DEFAULTS);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: EnquiryNoteWriteInput) => {
    setTopLevelError(null);
    try {
      await createMutation.mutateAsync(values);
      toast.success("Note added");
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
          <DialogTitle>Add note</DialogTitle>
          <DialogDescription>Notes are visible to staff.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="enq-note-body">Body</Label>
            <Textarea
              id="enq-note-body"
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
          <div className="space-y-2">
            <Label htmlFor="enq-note-kind">Kind</Label>
            <Select value={kindCtrl.field.value} onValueChange={kindCtrl.field.onChange}>
              <SelectTrigger id="enq-note-kind" aria-label="Kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ENQUIRY_NOTE_KIND_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Saving…" : "Add note"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function NotesTab() {
  const { enquiry } = useOutletContext<EnquiryOutletContext>();
  const notes = useEnquiryNotes(enquiry.id);
  const hasRole = useHasReservationsRole();

  const [kindFilter, setKindFilter] = useState<EnquiryNoteKind | typeof ALL_VALUE>(ALL_VALUE);
  const [createOpen, setCreateOpen] = useState(false);

  const filtered = useMemo(() => {
    const all = notes.data?.results ?? [];
    const matching = kindFilter === ALL_VALUE ? all : all.filter((n) => n.kind === kindFilter);
    return sortPinnedFirst(matching);
  }, [notes.data, kindFilter]);

  const handleKindChange = (value: string) => {
    if (value === ALL_VALUE) {
      setKindFilter(ALL_VALUE);
      return;
    }
    const parsed = enquiryNoteKindSchema.safeParse(value);
    if (parsed.success) setKindFilter(parsed.data);
  };

  const addButton = (
    <Button onClick={() => setCreateOpen(true)} disabled={!hasRole}>
      Add note
    </Button>
  );

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-foreground text-base font-semibold">Notes</h2>
        <div className="flex items-center gap-2">
          <Select value={kindFilter} onValueChange={handleKindChange}>
            <SelectTrigger className="w-[160px]" aria-label="Filter by kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KIND_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {hasRole ? (
            addButton
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>{addButton}</span>
              </TooltipTrigger>
              <TooltipContent>Reservations role required.</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      {notes.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : notes.isError ? (
        <ErrorState
          title="Couldn't load notes"
          description="Try again."
          onRetry={() => notes.refetch()}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No notes yet"
          description="Add a note to record context for this enquiry."
        />
      ) : (
        <ol className="space-y-2">
          {filtered.map((note) => (
            <li key={note.id} className="border-border bg-card space-y-2 rounded-lg border p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{ENQUIRY_NOTE_KIND_LABELS[note.kind]}</Badge>
                  {note.is_pinned ? <Badge variant="outline">Pinned</Badge> : null}
                </div>
              </div>
              <p className="text-foreground text-sm whitespace-pre-line">{note.body}</p>
              <p className="text-muted-foreground text-xs">
                {note.author != null ? `By #${note.author}` : "Unknown author"} ·{" "}
                {formatDate(note.created_at ?? null)}
              </p>
            </li>
          ))}
        </ol>
      )}

      {createOpen && (
        <NoteFormDialog enquiryId={enquiry.id} open={createOpen} onOpenChange={setCreateOpen} />
      )}
    </div>
  );
}
