import type { FieldPath, FieldValues, UseFormReturn } from "react-hook-form";
import i18n from "@/i18n";
import { ApiError } from "./errors";

export function applyApiErrorToForm<T extends FieldValues>(
  form: UseFormReturn<T>,
  error: unknown,
): { detail: string } {
  if (!(error instanceof ApiError)) {
    return { detail: i18n.t("common:errors.generic") };
  }
  const values = form.getValues();
  for (const [field, messages] of Object.entries(error.fieldErrors)) {
    if (field in values) {
      form.setError(field as FieldPath<T>, { message: messages.join(", ") });
    }
  }
  return { detail: error.detail };
}
