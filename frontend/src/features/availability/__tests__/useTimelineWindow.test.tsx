import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { addDays, format, startOfWeek } from "date-fns";
import { TIMELINE_WINDOW_DAYS, useTimelineWindow } from "../useTimelineWindow";

function wrapper(initialEntry: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
  );
}

const CURRENT_MONDAY = format(startOfWeek(new Date(), { weekStartsOn: 1 }), "yyyy-MM-dd");

describe("useTimelineWindow", () => {
  it("defaults to the current week's Monday over a 35-day window", () => {
    const { result } = renderHook(() => useTimelineWindow(), {
      wrapper: wrapper("/availability"),
    });
    expect(result.current.from).toBe(CURRENT_MONDAY);
    expect(result.current.days).toHaveLength(TIMELINE_WINDOW_DAYS);
    expect(result.current.to).toBe(
      format(addDays(new Date(result.current.from), TIMELINE_WINDOW_DAYS), "yyyy-MM-dd"),
    );
  });

  it("reads the window start from the `start` URL param", () => {
    const { result } = renderHook(() => useTimelineWindow(), {
      wrapper: wrapper("/availability?start=2026-06-08"),
    });
    expect(result.current.from).toBe("2026-06-08");
    expect(result.current.to).toBe("2026-07-13");
  });

  it("aligns a hand-edited non-Monday start down to Monday", () => {
    const { result } = renderHook(() => useTimelineWindow(), {
      wrapper: wrapper("/availability?start=2026-06-10"), // a Wednesday
    });
    expect(result.current.from).toBe("2026-06-08");
  });

  it("steps the window ±7 days and Today returns to the current Monday", () => {
    const { result } = renderHook(() => useTimelineWindow(), {
      wrapper: wrapper("/availability?start=2026-06-08"),
    });
    act(() => result.current.goNext());
    expect(result.current.from).toBe("2026-06-15");
    act(() => result.current.goPrev());
    act(() => result.current.goPrev());
    expect(result.current.from).toBe("2026-06-01");
    act(() => result.current.goToday());
    expect(result.current.from).toBe(CURRENT_MONDAY);
  });
});
