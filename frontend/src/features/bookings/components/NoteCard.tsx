import { PinIcon, PinOffIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format/date";
import { bookingNoteKindLabel, bookingNoteVisibilityLabel, type BookingNote } from "../schemas";

interface NoteCardProps {
  note: BookingNote;
  onTogglePin: () => void;
  onEdit: () => void;
  onDelete: () => void;
  pinDisabled?: boolean;
}

export function NoteCard({
  note,
  onTogglePin,
  onEdit,
  onDelete,
  pinDisabled = false,
}: NoteCardProps) {
  const { t } = useTranslation("bookings");
  const pinned = !!note.is_pinned;
  return (
    <li className="border-border bg-card space-y-2 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={pinned ? "secondary" : "ghost"}
            size="icon-sm"
            onClick={onTogglePin}
            disabled={pinDisabled}
            aria-pressed={pinned}
            aria-label={pinned ? t("notes.card.unpin_aria") : t("notes.card.pin_aria")}
          >
            {pinned ? <PinIcon /> : <PinOffIcon />}
          </Button>
          <Badge variant="secondary">{bookingNoteKindLabel(note.kind)}</Badge>
          <Badge variant="outline">{bookingNoteVisibilityLabel(note.visibility)}</Badge>
        </div>
        <div className="flex gap-1">
          <Button type="button" variant="ghost" size="sm" onClick={onEdit}>
            {t("common:actions.edit")}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onDelete}>
            {t("common:actions.delete")}
          </Button>
        </div>
      </div>
      <p className="text-foreground text-sm whitespace-pre-line">{note.body}</p>
      <p className="text-muted-foreground text-xs">
        {note.author
          ? t("notes.card.by_author", { id: note.author })
          : t("notes.card.unknown_author")}{" "}
        · {formatDate(note.created_at ?? null)}
      </p>
    </li>
  );
}
