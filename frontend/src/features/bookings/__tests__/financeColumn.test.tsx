import { describe, expect, it } from "vitest";
import type { CellContext, ColumnDef } from "@tanstack/react-table";
import { render, renderHook, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import i18n from "@/i18n";
import { useBookingColumns } from "../columns";
import type { BookingListItem } from "../schemas";

function financeCell(overrides: Partial<BookingListItem>) {
  const { result } = renderHook(() => useBookingColumns(), {
    wrapper: ({ children }) => <I18nextProvider i18n={i18n}>{children}</I18nextProvider>,
  });
  const column = result.current.find(
    (c) => (c as { id?: string }).id === "finance",
  ) as ColumnDef<BookingListItem> & {
    cell: (ctx: CellContext<BookingListItem, unknown>) => React.ReactNode;
  };
  const row = {
    reference: "VC-1",
    status: "confirmed",
    rental_price: "1000.00",
    balance_due: "0.00",
    currency_code: "EUR",
    total: "1000.00",
    ...overrides,
  } as BookingListItem;
  const cell = column.cell({ row: { original: row } } as CellContext<BookingListItem, unknown>);
  return render(<I18nextProvider i18n={i18n}>{cell}</I18nextProvider>);
}

describe("bookings finance column", () => {
  it("shows 'paid in full' when nothing is outstanding", () => {
    financeCell({ balance_due: "0.00" });
    expect(screen.getByText("Paid in full")).toBeInTheDocument();
  });

  it("shows the outstanding amount with a warning tone when due in future", () => {
    financeCell({ balance_due: "500.00", balance_due_at: "2999-01-01" });
    const due = screen.getByText(/due/i);
    expect(due).toHaveClass("text-warning");
  });

  it("shows the outstanding amount with a danger tone once overdue", () => {
    financeCell({ balance_due: "500.00", balance_due_at: "2000-01-01" });
    const due = screen.getByText(/due/i);
    expect(due).toHaveClass("text-danger");
  });
});
