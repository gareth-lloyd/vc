import { PinIcon, PinOffIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/format/date";
import {
  BOOKING_NOTE_KIND_LABELS,
  BOOKING_NOTE_VISIBILITY_LABELS,
  type BookingNote,
} from "../schemas";

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
            aria-label={pinned ? "Unpin note" : "Pin note"}
          >
            {pinned ? <PinIcon /> : <PinOffIcon />}
          </Button>
          <Badge variant="secondary">{BOOKING_NOTE_KIND_LABELS[note.kind]}</Badge>
          <Badge variant="outline">{BOOKING_NOTE_VISIBILITY_LABELS[note.visibility]}</Badge>
        </div>
        <div className="flex gap-1">
          <Button type="button" variant="ghost" size="sm" onClick={onEdit}>
            Edit
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onDelete}>
            Delete
          </Button>
        </div>
      </div>
      <p className="text-foreground text-sm whitespace-pre-line">{note.body}</p>
      <p className="text-muted-foreground text-xs">
        {note.author ? `By #${note.author}` : "Unknown author"} ·{" "}
        {formatDate(note.created_at ?? null)}
      </p>
    </li>
  );
}
