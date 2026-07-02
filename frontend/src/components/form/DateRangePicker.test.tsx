import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { renderWithProviders } from "@/test/render";
import { DateRangePicker, type DateRangePickerMode } from "./DateRangePicker";
import type { Matcher } from "react-day-picker";

interface RangeValues {
  date_from: string;
  date_to: string;
}

interface HarnessProps {
  mode: DateRangePickerMode;
  defaults?: RangeValues;
  onSubmit?: (values: RangeValues) => void;
  onPickerOpenChange?: (open: boolean) => void;
  disabledDays?: Matcher | Matcher[];
  excludeDisabled?: boolean;
  fromError?: string;
  toError?: string;
  disabled?: boolean;
  numberOfMonths?: 1 | 2;
}

const JULY_2026 = new Date(2026, 6, 1);

function Harness({ mode, defaults, onSubmit, ...pickerProps }: HarnessProps) {
  const form = useForm<RangeValues>({
    defaultValues: defaults ?? { date_from: "", date_to: "" },
  });
  return (
    <form onSubmit={form.handleSubmit((values) => onSubmit?.(values))} noValidate>
      <DateRangePicker
        control={form.control}
        fromName="date_from"
        toName="date_to"
        mode={mode}
        label="Dates"
        id="stay"
        fromLabel="From"
        toLabel="To"
        numberOfMonths={1}
        defaultMonth={JULY_2026}
        {...pickerProps}
      />
      <button type="submit">Submit</button>
    </form>
  );
}

function trigger() {
  return screen.getByRole("button", { name: /dates/i });
}

async function openPicker() {
  await userEvent.click(trigger());
  await screen.findByRole("grid");
}

describe("DateRangePicker trigger text", () => {
  it("shows the placeholder when empty", () => {
    renderWithProviders(<Harness mode="nights" />);
    expect(trigger()).toHaveTextContent("Select dates");
  });

  it("shows raw endpoints plus a nights count in nights mode", () => {
    renderWithProviders(
      <Harness mode="nights" defaults={{ date_from: "2026-07-12", date_to: "2026-07-19" }} />,
    );
    expect(trigger()).toHaveTextContent("12–19 Jul 2026 · 7 nights");
    // The selected range is part of the accessible name (label alone would
    // replace the button text for AT).
    expect(
      screen.getByRole("button", { name: /dates.*12–19 jul 2026 · 7 nights/i }),
    ).toBeInTheDocument();
  });

  it("falls back to the placeholder for an unparseable seeded start", () => {
    renderWithProviders(<Harness mode="nights" defaults={{ date_from: "garbage", date_to: "" }} />);
    expect(trigger()).toHaveTextContent("Select dates");
  });

  it("shows an inclusive days count in days mode", () => {
    renderWithProviders(
      <Harness mode="days" defaults={{ date_from: "2026-06-01", date_to: "2026-06-30" }} />,
    );
    expect(trigger()).toHaveTextContent("1–30 Jun 2026 · 30 days");
  });

  it("shows a single-day range as one day", () => {
    renderWithProviders(
      <Harness mode="days" defaults={{ date_from: "2026-06-01", date_to: "2026-06-01" }} />,
    );
    expect(trigger()).toHaveTextContent("1 Jun 2026 · 1 day");
  });

  it("shows an open end for a partial range", () => {
    renderWithProviders(
      <Harness mode="nights" defaults={{ date_from: "2026-07-12", date_to: "" }} />,
    );
    expect(trigger()).toHaveTextContent("12 Jul 2026 – …");
  });
});

describe("DateRangePicker selection", () => {
  it("writes a half-open range from an inclusive two-click nights selection", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<Harness mode="nights" onSubmit={onSubmit} />);
    await openPicker();
    await userEvent.click(screen.getByRole("button", { name: /21 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /25 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ date_from: "2026-07-21", date_to: "2026-07-26" }),
    );
  });

  it("writes the clicked endpoints verbatim in days mode", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<Harness mode="days" onSubmit={onSubmit} />);
    await openPicker();
    await userEvent.click(screen.getByRole("button", { name: /21 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /25 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ date_from: "2026-07-21", date_to: "2026-07-25" }),
    );
  });

  it("treats a single click as one night in nights mode", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<Harness mode="nights" onSubmit={onSubmit} />);
    await openPicker();
    await userEvent.click(screen.getByRole("button", { name: /21 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ date_from: "2026-07-21", date_to: "2026-07-22" }),
    );
  });

  it("treats a single click as a legal one-day range in days mode", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<Harness mode="days" onSubmit={onSubmit} />);
    await openPicker();
    await userEvent.click(screen.getByRole("button", { name: /21 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ date_from: "2026-07-21", date_to: "2026-07-21" }),
    );
  });

  // Pins react-day-picker v10's default addToRange semantics (resetOnSelect
  // stays off): a click after the end extends, a click inside shrinks the end.
  it("keeps the library's default extend/shrink re-click semantics", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <Harness
        mode="days"
        defaults={{ date_from: "2026-07-21", date_to: "2026-07-25" }}
        onSubmit={onSubmit}
      />,
    );
    await openPicker();
    // Click after the end → extends.
    await userEvent.click(screen.getByRole("button", { name: /27 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenLastCalledWith({ date_from: "2026-07-21", date_to: "2026-07-27" }),
    );
    // Submitting clicked outside the popover and closed it — reopen.
    await openPicker();
    // Click inside → shrinks the end.
    await userEvent.click(screen.getByRole("button", { name: /23 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenLastCalledWith({ date_from: "2026-07-21", date_to: "2026-07-23" }),
    );
  });
});

describe("DateRangePicker popover controls", () => {
  it("clears both fields and stays open on Clear", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <Harness
        mode="nights"
        defaults={{ date_from: "2026-07-12", date_to: "2026-07-19" }}
        onSubmit={onSubmit}
      />,
    );
    await openPicker();
    await userEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(screen.getByRole("grid")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ date_from: "", date_to: "" }));
  });

  it("closes the popover on Done", async () => {
    renderWithProviders(<Harness mode="nights" />);
    await openPicker();
    await userEvent.click(screen.getByRole("button", { name: /done/i }));
    await waitFor(() => expect(screen.queryByRole("grid")).not.toBeInTheDocument());
  });

  it("round-trips raw ISO values through the typed inputs", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(<Harness mode="nights" onSubmit={onSubmit} />);
    await openPicker();
    await userEvent.type(screen.getByLabelText(/^From$/), "2026-07-12");
    await userEvent.type(screen.getByLabelText(/^To$/), "2026-07-19");
    expect(trigger()).toHaveTextContent("12–19 Jul 2026 · 7 nights");
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ date_from: "2026-07-12", date_to: "2026-07-19" }),
    );
  });

  it("shows a live summary line with the picker's own testid", async () => {
    renderWithProviders(
      <Harness mode="nights" defaults={{ date_from: "2026-07-21", date_to: "2026-07-26" }} />,
    );
    await openPicker();
    // Half-open [21, 26) = 5 nights, last night the 25th.
    expect(screen.getByTestId("stay-summary")).toHaveTextContent("5 nights (21–25 Jul 2026)");
  });

  it("reports popover open state changes", async () => {
    const onPickerOpenChange = vi.fn();
    renderWithProviders(<Harness mode="nights" onPickerOpenChange={onPickerOpenChange} />);
    await openPicker();
    expect(onPickerOpenChange).toHaveBeenLastCalledWith(true);
    await userEvent.click(screen.getByRole("button", { name: /done/i }));
    expect(onPickerOpenChange).toHaveBeenLastCalledWith(false);
  });
});

describe("DateRangePicker disabled days", () => {
  it("greys out disabled days in the calendar", async () => {
    renderWithProviders(<Harness mode="nights" disabledDays={new Date(2026, 6, 23)} />);
    await openPicker();
    expect(screen.getByRole("button", { name: /23 july 2026/i })).toBeDisabled();
  });

  it("collapses a selection spanning a disabled day to the clicked day (nights)", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <Harness mode="nights" disabledDays={new Date(2026, 6, 23)} onSubmit={onSubmit} />,
    );
    await openPicker();
    await userEvent.click(screen.getByRole("button", { name: /21 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /25 july 2026/i }));
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));
    // excludeDisabled (defaulted on): the spanning range resets to the clicked
    // day rather than crossing the blocked 23rd.
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ date_from: "2026-07-25", date_to: "2026-07-26" }),
    );
  });
});

describe("DateRangePicker errors and disabling", () => {
  it("renders field errors outside the popover, visible while closed", () => {
    renderWithProviders(
      <Harness mode="nights" fromError="From is required" toError="To must be after From" />,
    );
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
    const alerts = screen.getAllByRole("alert");
    expect(alerts.map((alert) => alert.textContent)).toEqual([
      "From is required",
      "To must be after From",
    ]);
    expect(trigger()).toHaveAttribute("aria-invalid", "true");
    expect(trigger()).toHaveAttribute("aria-describedby", "stay-from-error stay-to-error");
  });

  it("disables the trigger when disabled", () => {
    renderWithProviders(<Harness mode="nights" disabled />);
    expect(trigger()).toBeDisabled();
  });
});

describe("DateRangePicker responsive months", () => {
  it("renders the explicit numberOfMonths", async () => {
    renderWithProviders(<Harness mode="nights" numberOfMonths={2} />);
    await userEvent.click(trigger());
    await waitFor(() => expect(screen.getAllByRole("grid")).toHaveLength(2));
  });
});

describe("DateRangePicker RHF integration", () => {
  it("reflects external setValue-style updates on the trigger", async () => {
    function ResetHarness() {
      const form = useForm<RangeValues>({ defaultValues: { date_from: "", date_to: "" } });
      const [, force] = useState(0);
      return (
        <>
          <DateRangePicker
            control={form.control}
            fromName="date_from"
            toName="date_to"
            mode="days"
            label="Dates"
            id="stay"
            fromLabel="From"
            toLabel="To"
            numberOfMonths={1}
            defaultMonth={JULY_2026}
          />
          <button
            type="button"
            onClick={() => {
              form.setValue("date_from", "2026-06-01");
              form.setValue("date_to", "2026-06-08");
              force((n) => n + 1);
            }}
          >
            Prefill
          </button>
        </>
      );
    }
    renderWithProviders(<ResetHarness />);
    await userEvent.click(screen.getByRole("button", { name: /prefill/i }));
    expect(trigger()).toHaveTextContent("1–8 Jun 2026 · 8 days");
  });
});
