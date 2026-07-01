import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { QuoteCriteriaForm } from "../components/QuoteCriteriaForm";

describe("QuoteCriteriaForm", () => {
  it("submits the arrival window + weeks translated to the wire criteria", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <QuoteCriteriaForm initial={{}} isSubmitting={false} onSubmit={onSubmit} />,
    );

    await userEvent.type(screen.getByLabelText(/arrive from/i), "2026-07-04");
    await userEvent.type(screen.getByLabelText(/arrive to/i), "2026-07-10");
    await userEvent.click(screen.getByRole("button", { name: /increase number of weeks/i }));
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));

    // W = 6 → flex 3, preferred arrival at the midpoint; 2 weeks = 14 nights.
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        date_from: "2026-07-07",
        date_to: "2026-07-21",
        flex_days: 3,
        adults: 2,
      }),
    );
  });

  it("hides Arrive-to when Search Specific Date is on and sends flex 0", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <QuoteCriteriaForm
        initial={{ arrive_from: "2026-07-04", arrive_to: "2026-07-10" }}
        isSubmitting={false}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByLabelText(/arrive to/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /search specific date/i }));
    expect(screen.queryByLabelText(/arrive to/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        date_from: "2026-07-04",
        date_to: "2026-07-11",
        flex_days: 0,
      }),
    );
  });

  it("blocks submit with an inline error when the window exceeds 42 days", async () => {
    const onSubmit = vi.fn();
    renderWithProviders(
      <QuoteCriteriaForm initial={{}} isSubmitting={false} onSubmit={onSubmit} />,
    );

    await userEvent.type(screen.getByLabelText(/arrive from/i), "2026-06-01");
    await userEvent.type(screen.getByLabelText(/arrive to/i), "2026-07-14");
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/at most 42 days/i);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("steps weeks down to a floor of one", async () => {
    renderWithProviders(<QuoteCriteriaForm initial={{}} isSubmitting={false} onSubmit={vi.fn()} />);

    const decrease = screen.getByRole("button", { name: /decrease number of weeks/i });
    expect(screen.getByText(/1 week$/i)).toBeInTheDocument();
    expect(decrease).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /increase number of weeks/i }));
    expect(screen.getByText(/2 weeks/i)).toBeInTheDocument();
    expect(decrease).toBeEnabled();
  });

  it("seeds from the provided initial values", () => {
    renderWithProviders(
      <QuoteCriteriaForm
        initial={{
          arrive_from: "2026-07-01",
          arrive_to: "2026-07-07",
          weeks: 2,
          specific_date: false,
          adults: 4,
        }}
        isSubmitting={false}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByLabelText(/arrive from/i)).toHaveValue("2026-07-01");
    expect(screen.getByLabelText(/arrive to/i)).toHaveValue("2026-07-07");
    expect(screen.getByText(/2 weeks/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/adults/i)).toHaveValue(4);
  });
});
