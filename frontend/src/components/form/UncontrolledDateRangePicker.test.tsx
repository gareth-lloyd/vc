import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { clickDateRange, openDateRange, typeDateRange } from "@/test/dateRange";
import {
  UncontrolledDateRangePicker,
  type UncontrolledDateRangePickerProps,
} from "./UncontrolledDateRangePicker";

type HarnessProps = Partial<UncontrolledDateRangePickerProps> & {
  initial?: { from: string; to: string };
  onEmit?: (from: string, to: string) => void;
  /** Uncontrolled-host mode: store the emitted value back into state. */
  storeBack?: boolean;
};

/** Mimics a real host: owns the value in state, passes a FRESH object literal
 * each render, and (optionally) writes emitted values back — the loop-prone
 * shape the wrapper must survive. Exposes a button to force an external reset. */
function Harness({
  initial = { from: "", to: "" },
  onEmit,
  storeBack = true,
  mode = "days",
  ...rest
}: HarnessProps) {
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  return (
    <div>
      <UncontrolledDateRangePicker
        id="probe-dates"
        mode={mode}
        label="Dates"
        fromLabel="From"
        toLabel="To"
        value={{ from, to }}
        onChange={(f, t) => {
          onEmit?.(f, t);
          if (storeBack) {
            setFrom(f);
            setTo(t);
          }
        }}
        {...rest}
      />
      <button
        type="button"
        onClick={() => {
          setFrom("");
          setTo("");
        }}
      >
        external clear
      </button>
    </div>
  );
}

const trigger = () => screen.getByRole("button", { name: /^Dates/ });

describe("UncontrolledDateRangePicker", () => {
  it("renders the controlled value on the trigger", () => {
    renderWithProviders(<Harness initial={{ from: "2026-06-01", to: "2026-06-30" }} />);
    expect(trigger()).toHaveTextContent("1–30 Jun 2026 · 30 days");
  });

  it("does not emit on mount", () => {
    const onEmit = vi.fn();
    renderWithProviders(
      <Harness initial={{ from: "2026-06-01", to: "2026-06-30" }} onEmit={onEmit} />,
    );
    expect(onEmit).not.toHaveBeenCalled();
  });

  it("emits the typed range (latest-wins final pair)", async () => {
    const user = userEvent.setup();
    const onEmit = vi.fn();
    renderWithProviders(<Harness onEmit={onEmit} />);

    const picker = await openDateRange(user, /^Dates/);
    await typeDateRange(user, picker, { from: "2026-06-01", to: "2026-06-30" });

    expect(onEmit).toHaveBeenCalled();
    expect(onEmit.mock.calls.at(-1)).toEqual(["2026-06-01", "2026-06-30"]);
  });

  it("emits a half-open pair from a nights calendar pick (final emitted pair)", async () => {
    const user = userEvent.setup();
    const onEmit = vi.fn();
    renderWithProviders(
      <Harness mode="nights" defaultMonth={new Date(2026, 6, 1)} onEmit={onEmit} />,
    );

    const picker = await openDateRange(user, /^Dates/);
    await clickDateRange(user, picker, /10 july 2026/i, /14 july 2026/i);

    // Inclusive nights 10–14 → stored half-open with checkout the 15th.
    expect(onEmit.mock.calls.at(-1)).toEqual(["2026-07-10", "2026-07-15"]);
  });

  it("emits empty strings when cleared", async () => {
    const user = userEvent.setup();
    const onEmit = vi.fn();
    renderWithProviders(
      <Harness initial={{ from: "2026-06-01", to: "2026-06-30" }} onEmit={onEmit} />,
    );

    const picker = await openDateRange(user, /^Dates/);
    await user.click(picker.getByRole("button", { name: /clear/i }));

    expect(onEmit.mock.calls.at(-1)).toEqual(["", ""]);
  });

  it("propagates an external value reset to the trigger without emitting", async () => {
    const user = userEvent.setup();
    const onEmit = vi.fn();
    renderWithProviders(
      <Harness initial={{ from: "2026-06-01", to: "2026-06-30" }} onEmit={onEmit} />,
    );
    expect(trigger()).toHaveTextContent("1–30 Jun 2026");

    await user.click(screen.getByRole("button", { name: /external clear/i }));

    expect(trigger()).toHaveTextContent("Select dates");
    // The external reset is a host-driven sync, not a user edit — no echo.
    expect(onEmit).not.toHaveBeenCalled();
  });
});
