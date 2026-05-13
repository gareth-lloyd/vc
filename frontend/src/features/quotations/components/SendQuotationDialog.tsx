import { useEffect, useState } from "react";
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
import { ApiError } from "@/lib/api/errors";
import { useSendQuotation } from "../hooks";
import type { QuotationDetail } from "../schemas";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quotation: QuotationDetail;
}

export function SendQuotationDialog({ open, onOpenChange, quotation }: Props) {
  const { t } = useTranslation("quotations");
  const send = useSendQuotation(quotation.id);
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  useEffect(() => {
    if (open) setTopLevelError(null);
  }, [open]);

  const handleConfirm = async () => {
    setTopLevelError(null);
    try {
      await send.mutateAsync();
      toast.success(t("detail.dialogs.send.toasts.success"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail);
      } else {
        toast.error(t("detail.dialogs.send.toasts.failed"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !send.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("detail.dialogs.send.title")}</DialogTitle>
          <DialogDescription>
            {t("detail.dialogs.send.description", { reference: quotation.reference })}
          </DialogDescription>
        </DialogHeader>

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
            disabled={send.isPending}
          >
            {t("detail.dialogs.send.cancel")}
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={send.isPending}>
            {send.isPending ? t("detail.dialogs.send.sending") : t("detail.dialogs.send.confirm")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
