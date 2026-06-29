import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ApiError } from "@/lib/api/errors";
import { logQueryError, shouldRetryQuery } from "./client";

function zodError(): z.ZodError {
  return z.object({ guest: z.number() }).safeParse({}).error!;
}

describe("shouldRetryQuery", () => {
  it("never retries a ZodError — a schema mismatch is deterministic", () => {
    expect(shouldRetryQuery(0, zodError())).toBe(false);
  });

  it("never retries a 4xx ApiError", () => {
    expect(shouldRetryQuery(0, new ApiError(404, null))).toBe(false);
  });

  it("retries a 5xx ApiError up to twice", () => {
    const err = new ApiError(500, null);
    expect(shouldRetryQuery(0, err)).toBe(true);
    expect(shouldRetryQuery(1, err)).toBe(true);
    expect(shouldRetryQuery(2, err)).toBe(false);
  });

  it("retries an unknown error up to twice", () => {
    const err = new Error("network down");
    expect(shouldRetryQuery(0, err)).toBe(true);
    expect(shouldRetryQuery(2, err)).toBe(false);
  });
});

describe("logQueryError", () => {
  let spy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    spy = vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    spy.mockRestore();
  });

  it("logs a ZodError with its prettified, field-level detail", () => {
    logQueryError("query", ["bookings", "list"], zodError());
    expect(spy).toHaveBeenCalledTimes(1);
    const [message, , detail] = spy.mock.calls[0];
    expect(message).toContain("schema validation");
    // z.prettifyError surfaces the offending field path.
    expect(String(detail)).toContain("guest");
  });

  it("logs unexpected (non-ApiError) errors", () => {
    logQueryError("query", ["x"], new Error("boom"));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("stays quiet for ApiErrors — they already surface in the UI and Network tab", () => {
    logQueryError("query", ["x"], new ApiError(500, null));
    expect(spy).not.toHaveBeenCalled();
  });
});
