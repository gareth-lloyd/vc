import { useEffect, useState } from "react";
import { useController, useForm } from "react-hook-form";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FormErrorAlert } from "@/components/feedback/FormErrorAlert";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";
import { useCreateBlockRequest } from "./hooks";
import {
  blockRequestWriteInputSchema,
  ownerBlockKindSchema,
  type BlockRequestWriteInput,
} from "./schemas";

interface Props {
  propertyId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function defaults(propertyId: number): BlockRequestWriteInput {
  return { property: propertyId, date_from: "", date_to: "", kind: "owner_stay", notes: "" };
}

export function BlockRequestDialog({ propertyId, open, onOpenChange }: Props) {
  const { t } = useTranslation("owner");
  const form = useForm<BlockRequestWriteInput>({
    resolver: zodResolver(blockRequestWriteInputSchema),
    defaultValues: defaults(propertyId),
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);
  const createMutation = useCreateBlockRequest();
  const kindCtrl = useController({ control: form.control, name: "kind" });

  useEffect(() => {
    if (open) {
      form.reset(defaults(propertyId));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, propertyId]);

  const handleSubmit = async (values: BlockRequestWriteInput) => {
    setTopLevelError(null);
    try {
      await createMutation.mutateAsync(values);
      toast.success(t("blocks.toasts.created"));
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
          <DialogTitle>{t("blocks.dialog.title")}</DialogTitle>
          <DialogDescription>{t("blocks.dialog.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="block-date-from">{t("blocks.fields.date_from")}</Label>
              <Input
                id="block-date-from"
                type="date"
                {...form.register("date_from")}
                aria-invalid={!!errors.date_from}
              />
              {errors.date_from ? (
                <p className="text-destructive text-sm" role="alert">
                  {t(errors.date_from.message ?? "")}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="block-date-to">{t("blocks.fields.date_to")}</Label>
              <Input
                id="block-date-to"
                type="date"
                {...form.register("date_to")}
                aria-invalid={!!errors.date_to}
              />
              {errors.date_to ? (
                <p className="text-destructive text-sm" role="alert">
                  {t(errors.date_to.message ?? "")}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="block-kind">{t("blocks.fields.kind")}</Label>
            <Select value={kindCtrl.field.value} onValueChange={kindCtrl.field.onChange}>
              <SelectTrigger id="block-kind" aria-label={t("blocks.fields.kind")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ownerBlockKindSchema.options.map((kind) => (
                  <SelectItem key={kind} value={kind}>
                    {t(`blocks.kind.${kind}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="block-notes">{t("blocks.fields.notes")}</Label>
            <Textarea id="block-notes" rows={3} {...form.register("notes")} />
          </div>

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
              {createMutation.isPending ? t("common:actions.saving") : t("blocks.actions.submit")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
