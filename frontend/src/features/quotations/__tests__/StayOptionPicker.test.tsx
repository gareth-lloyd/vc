import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import type { StayOption } from "../schemas";
import { StayOptionPicker } from "../components/StayOptionPicker";

function option(overrides: Partial<StayOption> = {}): StayOption {
  return {
    date_from: "2026-08-01",
    date_to: "2026-08-08",
    nights: 7,
    is_default: false,
    is_available: true,
    ...overrides,
  };
}

// Three consecutive 7-night blocks: default+available, held, available.
const UNIFORM: StayOption[] = [
  option({ date_from: "2026-08-01", date_to: "2026-08-08", is_default: true }),
  option({ date_from: "2026-08-08", date_to: "2026-08-15", is_available: false }),
  option({ date_from: "2026-08-15", date_to: "2026-08-22" }),
];

// Three all-available blocks — for exercising arrow wrap without held skips.
const AVAILABLE: StayOption[] = [
  option({ date_from: "2026-08-01", date_to: "2026-08-08", is_default: true }),
  option({ date_from: "2026-08-08", date_to: "2026-08-15" }),
  option({ date_from: "2026-08-15", date_to: "2026-08-22" }),
];

describe("StayOptionPicker", () => {
  it("renders one radio per option with the compact week label", () => {
    renderWithProviders(
      <StayOptionPicker options={UNIFORM} selectedIndex={0} onSelect={vi.fn()} />,
    );

    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    expect(screen.getByText("1–8 Aug")).toBeInTheDocument();
    expect(screen.getByText("8–15 Aug")).toBeInTheDocument();
    expect(screen.getByText("15–22 Aug")).toBeInTheDocument();
  });

  it("calls onSelect with the clicked index", async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <StayOptionPicker options={UNIFORM} selectedIndex={0} onSelect={onSelect} />,
    );

    await userEvent.click(screen.getAllByRole("radio")[2]);
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("drives aria-checked and a roving tabindex from selectedIndex", () => {
    renderWithProviders(
      <StayOptionPicker options={UNIFORM} selectedIndex={1} onSelect={vi.fn()} />,
    );

    const radios = screen.getAllByRole("radio");
    expect(radios[1]).toHaveAttribute("aria-checked", "true");
    expect(radios[0]).toHaveAttribute("aria-checked", "false");
    // Only the selected cell is tab-reachable; the rest are arrow-reachable.
    expect(radios[1]).toHaveAttribute("tabindex", "0");
    expect(radios[0]).toHaveAttribute("tabindex", "-1");
    expect(radios[2]).toHaveAttribute("tabindex", "-1");
  });

  it("moves selection with ArrowRight/ArrowLeft, wrapping at the ends", async () => {
    const onSelect = vi.fn();
    const { rerender } = renderWithProviders(
      <StayOptionPicker options={AVAILABLE} selectedIndex={0} onSelect={onSelect} />,
    );

    screen.getAllByRole("radio")[0].focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onSelect).toHaveBeenLastCalledWith(1);

    // ArrowLeft from the first cell wraps to the last.
    rerender(<StayOptionPicker options={AVAILABLE} selectedIndex={0} onSelect={onSelect} />);
    screen.getAllByRole("radio")[0].focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(onSelect).toHaveBeenLastCalledWith(2);
  });

  it("skips held cells when arrowing so selection only lands on bookable weeks", async () => {
    // UNIFORM index 1 is held; ArrowRight from index 0 jumps past it to index 2.
    const onSelect = vi.fn();
    renderWithProviders(
      <StayOptionPicker options={UNIFORM} selectedIndex={0} onSelect={onSelect} />,
    );

    screen.getAllByRole("radio")[0].focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onSelect).toHaveBeenLastCalledWith(2);
  });

  it("marks the default option Requested and the held option Held, held not selectable", async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <StayOptionPicker options={UNIFORM} selectedIndex={0} onSelect={onSelect} />,
    );

    const radios = screen.getAllByRole("radio");
    expect(within(radios[0]).getByText("Requested")).toBeInTheDocument();
    expect(within(radios[1]).getByText("Held")).toBeInTheDocument();
    // A booked week can't be quoted, so it isn't selectable — clicking is a no-op.
    expect(radios[1]).toBeDisabled();
    await userEvent.click(radios[1]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows both markers when the requested block is also held", () => {
    // The block nearest the guest's request can itself be held/booked — both
    // signals are meaningful, so the cell carries Requested and Held together.
    const requestedHeld: StayOption[] = [
      option({
        date_from: "2026-08-01",
        date_to: "2026-08-08",
        is_default: true,
        is_available: false,
      }),
      option({ date_from: "2026-08-08", date_to: "2026-08-15" }),
    ];
    renderWithProviders(
      <StayOptionPicker options={requestedHeld} selectedIndex={0} onSelect={vi.fn()} />,
    );

    const first = screen.getAllByRole("radio")[0];
    expect(within(first).getByText("Requested")).toBeInTheDocument();
    expect(within(first).getByText("Held")).toBeInTheDocument();
  });

  it("exposes a full-text aria-label per cell despite the abbreviated visible label", () => {
    renderWithProviders(
      <StayOptionPicker options={UNIFORM} selectedIndex={0} onSelect={vi.fn()} />,
    );

    expect(
      screen.getByRole("radio", { name: "1 Aug 2026 → 8 Aug 2026 · 7 nights · Available" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: "8 Aug 2026 → 15 Aug 2026 · 7 nights · Held" }),
    ).toBeInTheDocument();
  });

  it("shows one nights caption when all blocks share a length, no per-cell nights", () => {
    renderWithProviders(
      <StayOptionPicker options={UNIFORM} selectedIndex={0} onSelect={vi.fn()} />,
    );

    expect(screen.getByText("7-night stays")).toBeInTheDocument();
    // The per-cell "7 nights" sub-label is dropped when uniform (aria-label keeps it).
    expect(screen.queryByText("7 nights")).not.toBeInTheDocument();
  });

  it("keeps a per-cell nights sub-label when block lengths differ", () => {
    const mixed: StayOption[] = [
      option({ date_from: "2026-08-01", date_to: "2026-08-08", nights: 7, is_default: true }),
      option({ date_from: "2026-08-08", date_to: "2026-08-13", nights: 5 }),
    ];
    renderWithProviders(<StayOptionPicker options={mixed} selectedIndex={0} onSelect={vi.fn()} />);

    expect(screen.queryByText("7-night stays")).not.toBeInTheDocument();
    expect(screen.getByText("7 nights")).toBeInTheDocument();
    expect(screen.getByText("5 nights")).toBeInTheDocument();
  });
});
