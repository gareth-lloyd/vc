import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useDocumentTitle } from "./useDocumentTitle";

describe("useDocumentTitle", () => {
  beforeEach(() => {
    document.title = "seed";
  });

  it("sets the document title with the app-name suffix", () => {
    renderHook(() => useDocumentTitle("Bookings"));
    expect(document.title).toBe("Bookings · Villa Collective");
  });

  it("updates the title when the value changes", () => {
    const { rerender } = renderHook(({ title }) => useDocumentTitle(title), {
      initialProps: { title: "Bookings" },
    });
    expect(document.title).toBe("Bookings · Villa Collective");

    rerender({ title: "Dashboard" });
    expect(document.title).toBe("Dashboard · Villa Collective");
  });

  it("falls back to the bare app name for an empty title (never leaves a stale title)", () => {
    renderHook(() => useDocumentTitle(""));
    expect(document.title).toBe("Villa Collective");
  });
});
