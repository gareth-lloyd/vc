import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useContestBlock } from "./hooks";
import { contestWriteInputSchema, type ContestWriteInput } from "./schemas";

interface Props {
  updateId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DEFAULTS: ContestWriteInput = { reason: "" };

export function ContestDialog({ updateId, open, onOpenChange }: Props) {
  const { t } = useTranslation("owner");
  const form = useForm<ContestWriteInput>({
    resolver: zodResolver(contestWriteInputSchema),
    defaultValues: DEFAULTS,
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const contestMutation = useContestBlock();

  useEffect(() => {
    if (open) {
      form.reset(DEFAULTS);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, updateId]);

  const handleSubmit = async (values: ContestWriteInput) => {
    setTopLevelError(null);
    try {
      await contestMutation.mutateAsync({ id: updateId, reason: values.reason });
      toast.success(t("updates.toasts.contested"));
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

  const errors = form.formState.errors;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("updates.contest_dialog.title")}</DialogTitle>
          <DialogDescription>{t("updates.contest_dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="contest-reason">{t("updates.contest_dialog.reason_label")}</Label>
            <Textarea
              id="contest-reason"
              rows={3}
              {...form.register("reason")}
              aria-invalid={!!errors.reason}
            />
            {errors.reason ? (
              <p className="text-destructive text-sm" role="alert">
                {t(errors.reason.message ?? "")}
              </p>
            ) : null}
          </div>

          <FormErrorAlert message={topLevelError} />

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={contestMutation.isPending}
            >
              {t("common:actions.cancel")}
            </Button>
            <Button type="submit" disabled={contestMutation.isPending}>
              {contestMutation.isPending
                ? t("common:actions.saving")
                : t("updates.contest_dialog.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
