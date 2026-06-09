import type { FieldPath, FieldValues, UseFormReturn } from "react-hook-form";
import i18n from "@/i18n";
import { ApiError } from "./errors";

// DRF's reserved key for object-level (cross-field) validation errors.
const NON_FIELD_KEY = "non_field_errors";

// Flatten an arbitrarily-shaped DRF error value into plain strings. DRF returns
// string, string[], nested objects (`{city: [...]}`), and arrays of objects
// (nested serializers). Anything that isn't a string is recursed into so we
// never render `[object Object]` or throw on `.join`.
function flattenMessages(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(flattenMessages);
  if (value && typeof value === "object") return Object.values(value).flatMap(flattenMessages);
  return [];
}

// Maps an API 4xx error onto a form: matched flat fields become inline RHF
// errors; everything else (non_field_errors, nested objects, and fields with no
// inline home) is collected into the returned `detail` so it surfaces in the
// top-level alert instead of vanishing.
export function applyApiErrorToForm<T extends FieldValues>(
  form: UseFormReturn<T>,
  error: unknown,
): { detail: string } {
  if (!(error instanceof ApiError)) {
    return { detail: i18n.t("common:errors.generic") };
  }
  const values = form.getValues();
  const extras: string[] = [];
  for (const [field, raw] of Object.entries(error.fieldErrors)) {
    const messages = flattenMessages(raw);
    if (messages.length === 0) continue;
    if (field !== NON_FIELD_KEY && field in values) {
      form.setError(field as FieldPath<T>, { message: messages.join(", ") });
    } else {
      extras.push(...messages);
    }
  }
  return { detail: [error.detail, ...extras].filter(Boolean).join(" ") };
}
