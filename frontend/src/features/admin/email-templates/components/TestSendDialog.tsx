import { useCallback, useState } from "react";
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
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { ApiError } from "@/lib/api/errors";
import { ContextSourcePicker } from "./ContextSourcePicker";
import { useTestSendEmailTemplate } from "../hooks";
import { contextToRequest, type ContextSource } from "../schemas";

interface Props {
  templateKey: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TestSendDialog({ templateKey, open, onOpenChange }: Props) {
  const { t } = useTranslation("admin");
  const [to, setTo] = useState("");
  const [source, setSource] = useState<ContextSource>({ kind: "none" });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const handleSource = useCallback((next: ContextSource) => setSource(next), []);
  const mutation = useTestSendEmailTemplate(templateKey);

  const handleSubmit = async () => {
    setTopLevelError(null);
    try {
      const result = await mutation.mutateAsync({
        to: to.trim() || undefined,
        ...contextToRequest(source),
      });
      toast.success(t("email_templates.toasts.test_sent", { id: result.id }));
      onOpenChange(false);
    } catch (error) {
      // `to` is the only form field; surface a 4xx detail in the banner and a
      // 5xx as a toast (the dialog stays open so the operator can retry).
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail || t("email_templates.toasts.test_failed"));
      } else {
        toast.error(t("email_templates.toasts.test_failed"));
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !mutation.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("email_templates.test_send.title")}</DialogTitle>
          <DialogDescription>{t("email_templates.test_send.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="test-send-to">{t("email_templates.test_send.to_label")}</Label>
            <Input
              id="test-send-to"
              type="email"
              value={to}
              placeholder={t("email_templates.test_send.to_placeholder")}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>

          <ContextSourcePicker onChange={handleSource} />

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={mutation.isPending}>
              {mutation.isPending
                ? t("email_templates.test_send.sending")
                : t("email_templates.test_send.submit")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
