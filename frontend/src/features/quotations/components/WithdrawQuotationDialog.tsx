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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { useWithdrawQuotation } from "../hooks";
import type { QuotationDetail } from "../schemas";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quotation: QuotationDetail;
}

export function WithdrawQuotationDialog({ open, onOpenChange, quotation }: Props) {
  const { t } = useTranslation("quotations");
  const withdraw = useWithdrawQuotation(quotation.id);
  const [reason, setReason] = useState("");
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setReason("");
      setTopLevelError(null);
    }
  }, [open]);

  const handleConfirm = async () => {
    setTopLevelError(null);
    try {
      await withdraw.mutateAsync(reason.trim());
      toast.success(t("detail.dialogs.withdraw.toasts.success"));
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail);
      } else {
        toast.error(t("detail.dialogs.withdraw.toasts.failed"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !withdraw.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("detail.dialogs.withdraw.title")}</DialogTitle>
          <DialogDescription>
            {t("detail.dialogs.withdraw.description", { reference: quotation.reference })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="qw-reason">{t("detail.dialogs.withdraw.reason_label")}</Label>
          <Textarea
            id="qw-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("detail.dialogs.withdraw.reason_placeholder")}
            rows={3}
          />
        </div>

        <FormErrorAlert message={topLevelError} />

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={withdraw.isPending}
          >
            {t("detail.dialogs.withdraw.cancel")}
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleConfirm}
            disabled={withdraw.isPending}
          >
            {withdraw.isPending
              ? t("detail.dialogs.withdraw.withdrawing")
              : t("detail.dialogs.withdraw.confirm")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
