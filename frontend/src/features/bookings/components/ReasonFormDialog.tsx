import { useEffect, useState } from "react";
import { useForm, type DefaultValues, type FieldValues, type Path } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { ZodType } from "zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrorToForm } from "@/lib/api/forms";
import { ApiError } from "@/lib/api/errors";

export interface ReasonFormDialogProps<TInput extends FieldValues> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  schema: ZodType<TInput>;
  defaultValues: DefaultValues<TInput>;
  reasonField: Path<TInput>;
  submit: (values: TInput) => Promise<unknown>;
  isPending: boolean;
  title: string;
  description: string;
  reasonLabel: string;
  reasonId: string;
  submitLabel: string;
  busyLabel: string;
  keepLabel: string;
  successMessage: string;
}

export function ReasonFormDialog<TInput extends FieldValues>({
  open,
  onOpenChange,
  schema,
  defaultValues,
  reasonField,
  submit,
  isPending,
  title,
  description,
  reasonLabel,
  reasonId,
  submitLabel,
  busyLabel,
  keepLabel,
  successMessage,
}: ReasonFormDialogProps<TInput>) {
  const { t } = useTranslation("common");
  // zodResolver's generic signature doesn't infer cleanly through TInput's constraint
  // (it expects a stronger Zod3Type/FieldValues binding than ZodType<TInput> provides);
  // the cast is confined to this boundary.
  const form = useForm<TInput>({
    resolver: zodResolver(schema as never),
    defaultValues,
  });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      form.reset(defaultValues);
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSubmit = async (values: TInput) => {
    setTopLevelError(null);
    try {
      await submit(values);
      toast.success(successMessage);
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error(t("errors.generic"));
      }
    }
  };

  const fieldError = form.formState.errors[reasonField];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor={reasonId}>{reasonLabel}</Label>
            <Textarea
              id={reasonId}
              rows={4}
              autoFocus
              {...form.register(reasonField)}
              aria-invalid={!!fieldError}
            />
            {fieldError ? (
              <p className="text-destructive text-sm" role="alert">
                {fieldError.message as string}
              </p>
            ) : null}
          </div>

          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
              {keepLabel}
            </Button>
            <Button type="submit" variant="destructive" disabled={isPending}>
              {isPending ? busyLabel : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
