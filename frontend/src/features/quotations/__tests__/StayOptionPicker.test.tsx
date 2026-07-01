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

function renderPicker(
  options: StayOption[],
  {
    checked = new Set<number>([0]),
    onToggle = vi.fn(),
    staged = new Set<number>(),
  }: {
    checked?: Set<number>;
    onToggle?: ReturnType<typeof vi.fn>;
    staged?: Set<number>;
  } = {},
) {
  return renderWithProviders(
    <StayOptionPicker
      options={options}
      checkedIndices={checked}
      onToggle={onToggle}
      stagedIndices={staged}
    />,
  );
}

describe("StayOptionPicker", () => {
  it("renders one checkbox cell per option with the compact week label", () => {
    renderPicker(UNIFORM);

    const cells = screen.getAllByRole("checkbox");
    expect(cells).toHaveLength(3);
    expect(screen.getByText("1–8 Aug")).toBeInTheDocument();
    expect(screen.getByText("8–15 Aug")).toBeInTheDocument();
    expect(screen.getByText("15–22 Aug")).toBeInTheDocument();
  });

  it("toggles a cell on click and reflects multiple checked cells", async () => {
    const onToggle = vi.fn();
    renderPicker(AVAILABLE, { checked: new Set([0, 2]), onToggle });

    const cells = screen.getAllByRole("checkbox");
    expect(cells[0]).toHaveAttribute("aria-checked", "true");
    expect(cells[1]).toHaveAttribute("aria-checked", "false");
    expect(cells[2]).toHaveAttribute("aria-checked", "true");

    // Clicking any available cell toggles it — checked cells un-check.
    await userEvent.click(cells[1]);
    expect(onToggle).toHaveBeenLastCalledWith(1);
    await userEvent.click(cells[0]);
    expect(onToggle).toHaveBeenLastCalledWith(0);
  });

  it("toggles the focused cell with Space", async () => {
    const onToggle = vi.fn();
    renderPicker(AVAILABLE, { checked: new Set([0]), onToggle });

    screen.getAllByRole("checkbox")[0].focus();
    await userEvent.keyboard(" ");
    expect(onToggle).toHaveBeenLastCalledWith(0);
  });

  it("moves focus (not checks) with ArrowRight/ArrowLeft, wrapping and skipping held cells", async () => {
    const onToggle = vi.fn();
    renderPicker(UNIFORM, { checked: new Set([0]), onToggle });

    const cells = screen.getAllByRole("checkbox");
    cells[0].focus();
    // Index 1 is held → ArrowRight lands on index 2.
    await userEvent.keyboard("{ArrowRight}");
    expect(cells[2]).toHaveFocus();
    // ArrowRight from the last available wraps back to the first.
    await userEvent.keyboard("{ArrowRight}");
    expect(cells[0]).toHaveFocus();
    // Arrows never toggle.
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("keeps a roving tabindex: exactly one available cell is tab-reachable", () => {
    renderPicker(UNIFORM, { checked: new Set([0]) });

    const cells = screen.getAllByRole("checkbox");
    expect(cells[0]).toHaveAttribute("tabindex", "0");
    expect(cells[1]).toHaveAttribute("tabindex", "-1");
    expect(cells[2]).toHaveAttribute("tabindex", "-1");
  });

  it("marks the default option Requested and the held option Held, held not toggleable", async () => {
    const onToggle = vi.fn();
    renderPicker(UNIFORM, { checked: new Set([0]), onToggle });

    const cells = screen.getAllByRole("checkbox");
    expect(within(cells[0]).getByText("Requested")).toBeInTheDocument();
    expect(within(cells[1]).getByText("Held")).toBeInTheDocument();
    // A booked week can't be quoted, so it can't be checked — clicking is a no-op.
    expect(cells[1]).toBeDisabled();
    await userEvent.click(cells[1]);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("marks an already-staged week Added", () => {
    renderPicker(AVAILABLE, { checked: new Set([0]), staged: new Set([1]) });

    const cells = screen.getAllByRole("checkbox");
    expect(within(cells[1]).getByText("Added")).toBeInTheDocument();
    expect(within(cells[0]).queryByText("Added")).not.toBeInTheDocument();
  });

  it("shows both markers when the requested block is also held", () => {
    const requestedHeld: StayOption[] = [
      option({
        date_from: "2026-08-01",
        date_to: "2026-08-08",
        is_default: true,
        is_available: false,
      }),
      option({ date_from: "2026-08-08", date_to: "2026-08-15" }),
    ];
    renderPicker(requestedHeld, { checked: new Set([1]) });

    const first = screen.getAllByRole("checkbox")[0];
    expect(within(first).getByText("Requested")).toBeInTheDocument();
    expect(within(first).getByText("Held")).toBeInTheDocument();
  });

  it("exposes a full-text aria-label per cell despite the abbreviated visible label", () => {
    renderPicker(UNIFORM);

    expect(
      screen.getByRole("checkbox", { name: "1 Aug 2026 → 8 Aug 2026 · 7 nights · Available" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "8 Aug 2026 → 15 Aug 2026 · 7 nights · Held" }),
    ).toBeInTheDocument();
  });

  it("shows one nights caption when all blocks share a length, no per-cell nights", () => {
    renderPicker(UNIFORM);

    expect(screen.getByText("7-night stays")).toBeInTheDocument();
    // The per-cell "7 nights" sub-label is dropped when uniform (aria-label keeps it).
    expect(screen.queryByText("7 nights")).not.toBeInTheDocument();
  });

  it("keeps a per-cell nights sub-label when block lengths differ", () => {
    const mixed: StayOption[] = [
      option({ date_from: "2026-08-01", date_to: "2026-08-08", nights: 7, is_default: true }),
      option({ date_from: "2026-08-08", date_to: "2026-08-13", nights: 5 }),
    ];
    renderPicker(mixed);

    expect(screen.queryByText("7-night stays")).not.toBeInTheDocument();
    expect(screen.getByText("7 nights")).toBeInTheDocument();
    expect(screen.getByText("5 nights")).toBeInTheDocument();
  });
});
