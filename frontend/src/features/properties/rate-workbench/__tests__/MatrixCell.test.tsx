import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import type { RateBand } from "@/features/properties/schemas";
import type { MatrixCell as CellModel } from "../matrixModel";
import { MatrixCell } from "../components/MatrixCell";

const band = (o: Partial<RateBand>): RateBand => ({
  id: 11,
  period: 50,
  min_party: 2,
  max_party: 4,
  nightly: "200.00",
  weekly: "1400.00",
  ...o,
});

const cell = (b: RateBand): CellModel => ({
  band: b,
  fillable: false,
  periodId: 50,
  dateFrom: "2026-06-01",
  dateTo: "2026-06-28",
  minParty: 2,
  maxParty: 4,
});

const noop = {
  onCommitPrice: vi.fn(),
  onEditBand: vi.fn(),
  onFill: vi.fn(),
  onDeleteBand: vi.fn(),
};

function renderCell(b: RateBand) {
  return renderWithProviders(<MatrixCell cell={cell(b)} currencyCode="GBP" canWrite {...noop} />);
}

describe("MatrixCell — reductions (Q-018)", () => {
  it("shows the effective price with the base struck through when the band is reduced", () => {
    renderCell(
      band({
        reduction_percent: "20.00",
        reduced_at: "2026-05-01T09:00:00Z",
        effective_nightly: "160.00",
        effective_weekly: "1120.00",
      }),
    );
    // Struck-through base, muted.
    const struckNightly = screen.getByText("£200.00");
    expect(struckNightly.closest("s")).not.toBeNull();
    const struckWeekly = screen.getByText("£1,400.00");
    expect(struckWeekly.closest("s")).not.toBeNull();
    // Effective price shown alongside.
    expect(screen.getByText("£160.00")).toBeInTheDocument();
    expect(screen.getByText("£1,120.00")).toBeInTheDocument();
    // Compact reduction indicator.
    expect(screen.getByText("Reduced")).toBeInTheDocument();
  });

  it("keeps the inline editors on the BASE price when reduced", () => {
    renderCell(
      band({
        reduction_percent: "20.00",
        effective_nightly: "160.00",
        effective_weekly: "1120.00",
      }),
    );
    expect(screen.getByRole("textbox", { name: /Nightly rate/ })).toHaveValue("200.00");
    expect(screen.getByRole("textbox", { name: /Weekly rate/ })).toHaveValue("1400.00");
  });

  it("hints only the fields a fixed reduction actually reduces", () => {
    renderCell(
      band({
        reduced_nightly: "150.00",
        effective_nightly: "150.00",
        effective_weekly: "1400.00",
      }),
    );
    expect(screen.getByText("£150.00")).toBeInTheDocument();
    expect(screen.getByText("£200.00").closest("s")).not.toBeNull();
    // Weekly carries no reduction of its own → no struck weekly.
    expect(screen.queryByText("£1,400.00")).toBeNull();
  });

  it("shows no weekly hint when an optimistic base edit leaves effective_weekly stale (nightly-only fixed reduction)", () => {
    // The optimistic cache patches only the edited BASE field; effective_*
    // stays stale. The hint must key on the reduction fields, not on a
    // base-vs-effective string comparison.
    renderCell(
      band({
        reduced_nightly: "150.00",
        effective_nightly: "150.00",
        weekly: "1500.00", // edited base
        effective_weekly: "1400.00", // stale server value
      }),
    );
    // Nightly hint still shown (that axis IS reduced).
    expect(screen.getByText("£150.00")).toBeInTheDocument();
    // No phantom weekly hint: neither a struck edited base nor the stale effective.
    expect(screen.queryByText("£1,500.00")).toBeNull();
    expect(screen.queryByText("£1,400.00")).toBeNull();
  });

  it("recomputes a percent hint from the edited base rather than the stale effective", () => {
    renderCell(
      band({
        reduction_percent: "20.00",
        nightly: "300.00", // optimistically edited base
        effective_nightly: "160.00", // stale (from the old 200.00 base)
        weekly: null,
        effective_weekly: null,
      }),
    );
    expect(screen.getByText("£300.00").closest("s")).not.toBeNull();
    // 300 × (100 − 20) / 100 — coherent with the on-screen base.
    expect(screen.getByText("£240.00")).toBeInTheDocument();
    expect(screen.queryByText("£160.00")).toBeNull();
  });

  it("renders an unreduced band unchanged: no strike-through, no indicator", () => {
    renderCell(band({ effective_nightly: "200.00", effective_weekly: "1400.00" }));
    expect(document.querySelector("s")).toBeNull();
    expect(screen.queryByText("Reduced")).toBeNull();
    expect(screen.getByRole("textbox", { name: /Nightly rate/ })).toHaveValue("200.00");
  });
});
