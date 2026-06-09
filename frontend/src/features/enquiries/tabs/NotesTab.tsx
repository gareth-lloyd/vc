import { useEffect, useMemo, useState } from "react";
import { CheckboxLabel } from "@/components/ui/checkbox-label";
import { useTranslation } from "react-i18next";
import { useController, useForm } from "react-hook-form";
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
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { formatDate } from "@/lib/format/date";
import { useHasReservationsRole } from "@/lib/auth/useHasRole";
import { useCreateEnquiryNote, useEnquiryNotes } from "../hooks";
import {
  enquiryNoteKindLabel,
  enquiryNoteKindOptions,
  enquiryNoteKindSchema,
  enquiryNoteWriteInputSchema,
  type EnquiryNote,
  type EnquiryNoteKind,
  type EnquiryNoteWriteInput,
} from "../schemas";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";

const ALL_VALUE = "__all__";

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
  const { t } = useTranslation("enquiries");
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
      toast.success(t("notes.form_dialog.success_message"));
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
          <DialogTitle>{t("notes.form_dialog.title")}</DialogTitle>
          <DialogDescription>{t("notes.form_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="enq-note-body">{t("notes.form_dialog.fields.body")}</Label>
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
            <Label htmlFor="enq-note-kind">{t("notes.form_dialog.fields.kind")}</Label>
            <Select value={kindCtrl.field.value} onValueChange={kindCtrl.field.onChange}>
              <SelectTrigger
                id="enq-note-kind"
                aria-label={t("notes.form_dialog.fields.kind_aria")}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {enquiryNoteKindOptions().map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <CheckboxLabel>
            <Checkbox
              checked={!!pinnedCtrl.field.value}
              onCheckedChange={(v) => pinnedCtrl.field.onChange(v === true)}
            />
            <span>{t("notes.form_dialog.fields.pin")}</span>
          </CheckboxLabel>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending
                ? t("common:actions.saving")
                : t("notes.form_dialog.submit_label")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function NotesTab({ enquiryId }: { enquiryId: number }) {
  const { t } = useTranslation("enquiries");
  const notes = useEnquiryNotes(enquiryId);
  const hasRole = useHasReservationsRole();

  const [kindFilter, setKindFilter] = useState<EnquiryNoteKind | typeof ALL_VALUE>(ALL_VALUE);
  const [createOpen, setCreateOpen] = useState(false);

  const filtered = useMemo(() => {
    const all = notes.data?.results ?? [];
    const matching = kindFilter === ALL_VALUE ? all : all.filter((n) => n.kind === kindFilter);
    return sortPinnedFirst(matching);
  }, [notes.data, kindFilter]);

  const kindOptions = [
    { value: ALL_VALUE, label: t("notes.all_kinds") },
    ...enquiryNoteKindOptions(),
  ];

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
      {t("notes.add_button")}
    </Button>
  );

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
          {hasRole ? (
            addButton
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>{addButton}</span>
              </TooltipTrigger>
              <TooltipContent>{t("common:errors.reservations_role_required")}</TooltipContent>
            </Tooltip>
          )}
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
            <li key={note.id} className="border-border bg-card space-y-2 rounded-lg border p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{enquiryNoteKindLabel(note.kind)}</Badge>
                  {note.is_pinned ? (
                    <Badge variant="outline">{t("notes.pinned_badge")}</Badge>
                  ) : null}
                </div>
              </div>
              <p className="text-foreground text-sm whitespace-pre-line">{note.body}</p>
              <p className="text-muted-foreground text-xs">
                {note.author != null
                  ? t("notes.by_author", { id: note.author })
                  : t("notes.unknown_author")}{" "}
                · {formatDate(note.created_at ?? null)}
              </p>
            </li>
          ))}
        </ol>
      )}

      {createOpen && (
        <NoteFormDialog enquiryId={enquiryId} open={createOpen} onOpenChange={setCreateOpen} />
      )}
    </div>
  );
}
