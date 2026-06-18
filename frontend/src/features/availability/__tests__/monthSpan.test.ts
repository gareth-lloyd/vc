import { describe, expect, it } from "vitest";
import { parseISO } from "date-fns";
import { enGB } from "date-fns/locale";
import i18n from "@/i18n";
import { monthSpanLabel } from "../monthSpan";

const t = i18n.getFixedT("en", "availability");
const span = (from: string, to: string) => monthSpanLabel(parseISO(from), parseISO(to), t, enGB);

describe("monthSpanLabel", () => {
  it("renders a single month + year when the window stays in one month", () => {
    expect(span("2026-06-01", "2026-06-28")).toBe("June 2026");
  });

  it("renders both months once when the window crosses a month boundary in one year", () => {
    expect(span("2026-06-15", "2026-07-19")).toBe("June – July 2026");
  });

  it("repeats the year on each side when the window crosses a year boundary", () => {
    expect(span("2025-12-15", "2026-01-18")).toBe("December 2025 – January 2026");
  });
});
