import type { FieldPath, FieldValues, UseFormReturn } from "react-hook-form";
import { ApiError } from "./errors";

export function applyApiErrorToForm<T extends FieldValues>(
  form: UseFormReturn<T>,
  error: unknown,
): { detail: string } {
  if (!(error instanceof ApiError)) {
    return { detail: "Something went wrong. Please try again." };
  }
  const values = form.getValues();
  for (const [field, messages] of Object.entries(error.fieldErrors)) {
    if (field in values) {
      form.setError(field as FieldPath<T>, { message: messages.join(", ") });
    }
  }
  return { detail: error.detail };
}
