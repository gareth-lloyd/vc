import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/feedback/ErrorState";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useCopyToClipboard } from "@/lib/clipboard/useCopyToClipboard";
import { htmlToPlainText } from "@/lib/clipboard/htmlToPlainText";
import { useMarkQuotationManuallySent, useQuotationPreview, useSendQuotation } from "../hooks";
import {
  quotationSendOverridesSchema,
  type QuotationDetail,
  type QuotationSendOverrides,
} from "../schemas";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quotation: QuotationDetail;
}

const EMPTY: QuotationSendOverrides = { subject: "", intro: "", signoff: "" };

export function SendPreviewDialog({ open, onOpenChange, quotation }: Props) {
  const { t } = useTranslation("quotations");
  const send = useSendQuotation(quotation.id);
  const markManuallySent = useMarkQuotationManuallySent(quotation.id);
  const { copy } = useCopyToClipboard();
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const form = useForm<QuotationSendOverrides>({
    resolver: zodResolver(quotationSendOverridesSchema),
    defaultValues: EMPTY,
  });

  // Watch the editable fields so the preview can re-render the operator's
  // edits live. We seed once from the server defaults (no overrides) and only
  // start passing overrides once that seed has landed — otherwise the first
  // fetch would post empty strings before we know the defaults.
  const [seeded, setSeeded] = useState(false);
  const subject = form.watch("subject");
  const intro = form.watch("intro");
  const signoff = form.watch("signoff");

  // Debounce the watched values so each keystroke doesn't refire the preview.
  const [debounced, setDebounced] = useState<QuotationSendOverrides>(EMPTY);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced({ subject, intro, signoff }), 350);
    return () => clearTimeout(handle);
  }, [subject, intro, signoff]);

  // Pass overrides only once the form is seeded; before that we want the
  // server's stored defaults so the editable fields can be populated.
  const preview = useQuotationPreview(quotation.id, open, seeded ? debounced : undefined);
  const previewData = preview.data;

  // Seed the editable fields from the preview defaults once they load.
  useEffect(() => {
    if (open && previewData && !seeded) {
      form.reset({
        subject: previewData.subject,
        intro: previewData.intro,
        signoff: previewData.signoff,
      });
      setDebounced({
        subject: previewData.subject,
        intro: previewData.intro,
        signoff: previewData.signoff,
      });
      setTopLevelError(null);
      setSeeded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, previewData, seeded]);

  // Reset the seed latch when the dialog closes so a re-open starts fresh.
  useEffect(() => {
    if (!open) setSeeded(false);
  }, [open]);

  const busy = send.isPending || markManuallySent.isPending;

  const handleSubmit = async (values: QuotationSendOverrides) => {
    setTopLevelError(null);
    try {
      await send.mutateAsync(values);
      toast.success(t("detail.dialogs.send_preview.toasts.success"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("detail.dialogs.send_preview.toasts.failed"));
      }
    }
  };

  // Path B — copy the already-loaded HTML, then record the SENT state so the
  // Outlook flow mirrors Path A's bookkeeping. The clipboard write MUST stay
  // synchronous within the click handler (no awaited fetch first) or Safari /
  // Firefox drop the transient-activation window and throw NotAllowedError.
  // Because the preview is kept in sync with the operator's edits (Fix A),
  // `previewData.html` is already the edited content.
  const handleCopy = async () => {
    if (!previewData) return;
    // Synchronous: reach clipboard.write inside the click's user activation.
    const copied = copy(previewData.html, htmlToPlainText(previewData.html));
    try {
      const ok = await copied;
      if (!ok) {
        toast.error(t("detail.dialogs.send_preview.toasts.copy_failed"));
        return;
      }
      await markManuallySent.mutateAsync();
      toast.success(t("detail.dialogs.send_preview.toasts.copied"));
      onOpenChange(false);
    } catch (error) {
      const message =
        error instanceof ApiError && error.detail
          ? error.detail
          : t("detail.dialogs.send_preview.toasts.copy_failed");
      toast.error(message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("detail.dialogs.send_preview.title")}</DialogTitle>
          <DialogDescription>
            {t("detail.dialogs.send_preview.description", { reference: quotation.reference })}
          </DialogDescription>
        </DialogHeader>

        {preview.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : preview.isError || !previewData ? (
          <ErrorState
            description={t("detail.dialogs.send_preview.preview_error")}
            onRetry={() => preview.refetch()}
            retrying={preview.isFetching}
          />
        ) : (
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
            <div className="space-y-2">
              <p className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                {t("detail.dialogs.send_preview.preview_heading")}
              </p>
              <iframe
                title={t("detail.dialogs.send_preview.preview_title")}
                srcDoc={previewData.html}
                sandbox=""
                className="border-border h-72 w-full rounded-md border"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="qsp-subject">{t("detail.dialogs.send_preview.fields.subject")}</Label>
              <Input id="qsp-subject" {...form.register("subject")} />
              {form.formState.errors.subject ? (
                <p className="text-destructive text-xs">{form.formState.errors.subject.message}</p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="qsp-intro">{t("detail.dialogs.send_preview.fields.intro")}</Label>
              <Textarea id="qsp-intro" rows={3} {...form.register("intro")} />
              {form.formState.errors.intro ? (
                <p className="text-destructive text-xs">{form.formState.errors.intro.message}</p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="qsp-signoff">{t("detail.dialogs.send_preview.fields.signoff")}</Label>
              <Textarea id="qsp-signoff" rows={2} {...form.register("signoff")} />
              {form.formState.errors.signoff ? (
                <p className="text-destructive text-xs">{form.formState.errors.signoff.message}</p>
              ) : null}
            </div>

            <FormErrorAlert message={topLevelError} />

            <div className="flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={busy}
              >
                {t("detail.dialogs.send_preview.cancel")}
              </Button>
              <Button type="button" variant="secondary" onClick={handleCopy} disabled={busy}>
                {markManuallySent.isPending
                  ? t("detail.dialogs.send_preview.copying")
                  : t("detail.dialogs.send_preview.copy")}
              </Button>
              <Button type="submit" disabled={busy}>
                {send.isPending
                  ? t("detail.dialogs.send_preview.sending")
                  : t("detail.dialogs.send_preview.confirm")}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
