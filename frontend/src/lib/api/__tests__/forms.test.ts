import { describe, expect, it, vi } from "vitest";
import type { UseFormReturn } from "react-hook-form";
import { ApiError } from "../errors";
import { applyApiErrorToForm } from "../forms";

// Minimal RHF stub: getValues returns the known form fields; setError records.
function makeForm(fields: Record<string, unknown>) {
  const setError = vi.fn();
  const form = {
    getValues: () => fields,
    setError,
  } as unknown as UseFormReturn<Record<string, unknown>>;
  return { form, setError };
}

function apiError(body: Record<string, unknown>): ApiError {
  return new ApiError(400, { detail: "Please fix the errors.", ...body });
}

describe("applyApiErrorToForm", () => {
  it("maps a matched flat field error to an inline RHF error", () => {
    const { form, setError } = makeForm({ email: "" });
    const { detail } = applyApiErrorToForm(
      form,
      apiError({ field_errors: { email: ["Required."] } }),
    );
    expect(setError).toHaveBeenCalledWith("email", { message: "Required." });
    expect(detail).toBe("Please fix the errors.");
  });

  it("surfaces non_field_errors in detail without a field-name prefix", () => {
    const { form, setError } = makeForm({ email: "" });
    const { detail } = applyApiErrorToForm(
      form,
      apiError({ field_errors: { non_field_errors: ["Dates overlap an existing booking."] } }),
    );
    expect(setError).not.toHaveBeenCalled();
    expect(detail).toContain("Dates overlap an existing booking.");
    expect(detail).not.toContain("non_field_errors");
  });

  it("flattens nested serializer errors instead of rendering [object Object]", () => {
    const { form } = makeForm({ name: "" });
    const { detail } = applyApiErrorToForm(
      form,
      apiError({ field_errors: { address: { city: ["This field is required."] } } }),
    );
    expect(detail).toContain("This field is required.");
    expect(detail).not.toContain("[object Object]");
  });

  it("surfaces an unmatched field's error in detail rather than dropping it", () => {
    const { form, setError } = makeForm({ name: "" });
    const { detail } = applyApiErrorToForm(
      form,
      apiError({ field_errors: { body_template_html: ["Template failed to compile."] } }),
    );
    expect(setError).not.toHaveBeenCalled();
    expect(detail).toContain("Template failed to compile.");
  });

  it("returns the generic message for a non-ApiError", () => {
    const { form } = makeForm({});
    const { detail } = applyApiErrorToForm(form, new Error("boom"));
    expect(detail).toBeTruthy();
  });
});
