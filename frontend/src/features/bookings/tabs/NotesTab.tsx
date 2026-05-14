import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { ApiError } from "@/lib/api/errors";
import { useBookingNotes, useDeleteBookingNote, useToggleBookingNotePin } from "../hooks";
import { NoteCard } from "../components/NoteCard";
import { NoteFormDialog } from "../components/NoteFormDialog";
import {
  bookingNoteKindOptions,
  bookingNoteKindSchema,
  type BookingNote,
  type BookingNoteKind,
} from "../schemas";
import type { BookingOutletContext } from "../BookingDetailLayout";

const ALL_VALUE = "__all__";

function sortPinnedFirst(notes: readonly BookingNote[]): BookingNote[] {
  return [...notes].sort((a, b) => {
    const ap = a.is_pinned ? 0 : 1;
    const bp = b.is_pinned ? 0 : 1;
    if (ap !== bp) return ap - bp;
    return (a.created_at ?? "").localeCompare(b.created_at ?? "");
  });
}

export function NotesTab() {
  const { t } = useTranslation("bookings");
  const { booking } = useOutletContext<BookingOutletContext>();
  const notes = useBookingNotes(booking.id);
  const togglePin = useToggleBookingNotePin(booking.id);
  const deleteNote = useDeleteBookingNote(booking.id);

  const [kindFilter, setKindFilter] = useState<BookingNoteKind | typeof ALL_VALUE>(ALL_VALUE);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<BookingNote | null>(null);
  const [deleting, setDeleting] = useState<BookingNote | null>(null);

  const kindOptions = useMemo(
    () => [{ value: ALL_VALUE, label: t("notes.all_kinds") }, ...bookingNoteKindOptions()],
    [t],
  );

  const filtered = useMemo(() => {
    const all = notes.data?.results ?? [];
    const matching = kindFilter === ALL_VALUE ? all : all.filter((n) => n.kind === kindFilter);
    return sortPinnedFirst(matching);
  }, [notes.data, kindFilter]);

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteNote.mutateAsync({ noteId: deleting.id });
      toast.success(t("notes.toasts.deleted"));
      setDeleting(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.detail : t("notes.toasts.delete_failed");
      toast.error(message);
    }
  };

  const handleKindChange = (value: string) => {
    if (value === ALL_VALUE) {
      setKindFilter(ALL_VALUE);
      return;
    }
    const parsed = bookingNoteKindSchema.safeParse(value);
    if (parsed.success) setKindFilter(parsed.data);
  };

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-foreground text-base font-semibold">{t("notes.heading")}</h2>
        <div className="flex items-center gap-2">
          <Select value={kindFilter} onValueChange={handleKindChange}>
            <SelectTrigger className="w-[160px]" aria-label={t("notes.filter_kind_aria")}>
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
          <Button onClick={() => setCreateOpen(true)}>{t("notes.add_note")}</Button>
        </div>
      </div>

      {notes.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : notes.isError ? (
        <ErrorState
          title={t("notes.load_failed_title")}
          description={t("notes.load_failed_body")}
          onRetry={() => notes.refetch()}
        />
      ) : filtered.length === 0 ? (
        <EmptyState title={t("notes.empty_title")} description={t("notes.empty_body")} />
      ) : (
        <ol className="space-y-2">
          {filtered.map((note) => (
            <NoteCard
              key={note.id}
              note={note}
              onTogglePin={() => togglePin.mutate({ noteId: note.id, is_pinned: !note.is_pinned })}
              onEdit={() => setEditing(note)}
              onDelete={() => setDeleting(note)}
            />
          ))}
        </ol>
      )}

      <NoteFormDialog
        mode="create"
        bookingId={booking.id}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />

      {editing ? (
        <NoteFormDialog
          mode="edit"
          bookingId={booking.id}
          note={editing}
          open={true}
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        onConfirm={handleDelete}
        title={t("notes.confirm_delete.title")}
        description={t("notes.confirm_delete.description")}
        confirmLabel={t("common:actions.delete")}
        destructive
        busy={deleteNote.isPending}
      />
    </div>
  );
}
