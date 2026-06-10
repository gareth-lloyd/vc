import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { QuoteCart } from "../components/QuoteCart";
import type { StagedLine } from "../schemas";

function stagedLine(overrides: Partial<StagedLine> = {}): StagedLine {
  return {
    property_id: 7,
    property_name: "Villa Sol",
    hero_image_url: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    priced_date_from: "2026-07-01",
    priced_date_to: "2026-07-08",
    adults: 2,
    children: 0,
    currency: "USD",
    total: "4500.00",
    discount: "0",
    inclusions: "",
    price_override_reason: "",
    is_manual: false,
    manual_only: false,
    notes: "",
    ...overrides,
  };
}

// A no-rate villa staged from the builder (Q-013): manual from the start,
// no engine total to fall back to.
function noRateLine(overrides: Partial<StagedLine> = {}): StagedLine {
  return stagedLine({
    total: null,
    currency: "EUR",
    is_manual: true,
    manual_only: true,
    ...overrides,
  });
}

// Controlled wrapper: the page owns the staged lines, so the cart only edits
// via callbacks. Mirror that here so discount edits actually re-render.
function Harness({ initial }: { initial: StagedLine[] }) {
  const [lines, setLines] = useState(initial);
  return (
    <QuoteCart
      lines={lines}
      onUpdateLine={(id, patch) =>
        setLines((prev) => prev.map((l) => (l.property_id === id ? { ...l, ...patch } : l)))
      }
      onRemove={(id) => setLines((prev) => prev.filter((l) => l.property_id !== id))}
      onSaveDraft={() => undefined}
      onSendToGuest={() => undefined}
    />
  );
}

beforeEach(() => {
  useAuthStore.setState({ role: "RESERVATIONS", isSuperuser: false, status: "authenticated" });
});
afterEach(() => {
  useAuthStore.getState().clear();
});

describe("QuoteCart", () => {
  it("lists the staged lines with their own totals and never sums a cart-level total", () => {
    renderWithProviders(
      <Harness
        initial={[
          stagedLine(),
          stagedLine({ property_id: 8, property_name: "Villa Azul", total: "7200.00" }),
        ]}
      />,
    );
    expect(screen.getByText("Villa Sol")).toBeInTheDocument();
    expect(screen.getByText("Villa Azul")).toBeInTheDocument();
    // Each line carries its own price; the cart never sums them, because the
    // guest picks one villa from the shortlist — not all of them.
    expect(screen.getByText("$4,500.00")).toBeInTheDocument();
    expect(screen.getByText("$7,200.00")).toBeInTheDocument();
    expect(screen.queryByText("$11,700.00")).not.toBeInTheDocument();
  });

  it("renders mixed-currency lines each in their own currency", () => {
    // Currency travels per line (GAP-014) — a cart can mix £/€ side by side.
    renderWithProviders(
      <Harness
        initial={[
          stagedLine({ currency: "GBP" }),
          stagedLine({
            property_id: 8,
            property_name: "Villa Azul",
            total: "7200.00",
            currency: "EUR",
          }),
        ]}
      />,
    );
    expect(screen.getByText("£4,500.00")).toBeInTheDocument();
    expect(screen.getByText("€7,200.00")).toBeInTheDocument();
  });

  it("applies a discount to the line total", async () => {
    renderWithProviders(
      <Harness
        initial={[
          stagedLine(),
          stagedLine({ property_id: 8, property_name: "Villa Azul", total: "7200.00" }),
        ]}
      />,
    );

    // Expand the first line and discount it by 500.
    await userEvent.click(screen.getAllByRole("button", { name: /edit line/i })[0]);
    const discount = screen.getByLabelText(/^discount$/i);
    await userEvent.clear(discount);
    await userEvent.type(discount, "500");

    // 4500 − 500 = 4000 on the line; the other line is untouched.
    expect(screen.getByText("$4,000.00")).toBeInTheDocument();
    expect(screen.getByText("$7,200.00")).toBeInTheDocument();
  });

  it("blocks the commit actions until a manual override has a total and reason", async () => {
    renderWithProviders(<Harness initial={[stagedLine()]} />);

    await userEvent.click(screen.getByRole("button", { name: /edit line/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /override the price manually/i }));

    // Manual on, but total + reason blank → commit blocked.
    expect(screen.getByRole("button", { name: /save draft/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/manual total/i), "5000");
    await userEvent.type(screen.getByLabelText(/reason for price override/i), "Agreed rate");

    expect(screen.getByRole("button", { name: /save draft/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeEnabled();
  });

  it("renders the priced date range and guest count for a line", () => {
    renderWithProviders(<Harness initial={[stagedLine({ adults: 2, children: 1 })]} />);
    expect(screen.getByText(/1 Jul 2026 – 8 Jul 2026/i)).toBeInTheDocument();
    expect(screen.getByText(/2A · 1C/)).toBeInTheDocument();
  });

  it("blocks the commit actions and shows an inline error for a non-numeric discount", async () => {
    renderWithProviders(<Harness initial={[stagedLine()]} />);

    await userEvent.click(screen.getByRole("button", { name: /edit line/i }));
    const discount = screen.getByLabelText(/^discount$/i);
    await userEvent.clear(discount);
    await userEvent.type(discount, "abc");

    expect(screen.getByText(/enter a valid discount amount/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save draft/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeDisabled();
  });

  it("blocks the commit actions for a priced line that has no engine total", () => {
    renderWithProviders(<Harness initial={[stagedLine({ total: null })]} />);

    // An available option that arrived without a price contributes nothing to
    // the subtotal, so it must not be silently saveable.
    expect(screen.getByText(/this option has no price/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save draft/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeDisabled();
  });

  it("auto-expands a newly staged no-rate manual line onto its total/reason inputs", () => {
    renderWithProviders(<Harness initial={[noRateLine()]} />);
    // No click needed — the operator lands straight on the inputs they must fill.
    expect(screen.getByLabelText(/manual total/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/reason for price override/i)).toBeInTheDocument();
    // The line's currency is shown beside the total so the operator knows what
    // they're typing (the backend resolves it server-side on save).
    expect(screen.getByText("EUR")).toBeInTheDocument();
  });

  it("stays collapsed after the user collapses an auto-expanded line", async () => {
    renderWithProviders(<Harness initial={[noRateLine()]} />);
    await userEvent.click(screen.getByRole("button", { name: /collapse line/i }));
    expect(screen.queryByLabelText(/manual total/i)).not.toBeInTheDocument();

    // Editing another line (a re-render with the same staged ids) must not
    // re-expand the collapsed one.
    expect(screen.queryByLabelText(/manual total/i)).not.toBeInTheDocument();
  });

  it("auto-expands again when a removed manual line is re-staged", async () => {
    // Remove + re-add is a fresh staging: the guided entry must fire again.
    function RemoveReAddHarness() {
      const [lines, setLines] = useState<StagedLine[]>([noRateLine()]);
      return (
        <>
          <button type="button" onClick={() => setLines([noRateLine()])}>
            restage
          </button>
          <QuoteCart
            lines={lines}
            onUpdateLine={(id, patch) =>
              setLines((prev) => prev.map((l) => (l.property_id === id ? { ...l, ...patch } : l)))
            }
            onRemove={(id) => setLines((prev) => prev.filter((l) => l.property_id !== id))}
            onSaveDraft={() => undefined}
            onSendToGuest={() => undefined}
          />
        </>
      );
    }
    renderWithProviders(<RemoveReAddHarness />);
    expect(screen.getByLabelText(/manual total/i)).toBeInTheDocument();

    // Collapse first — otherwise a stale expandedId masks the regression.
    await userEvent.click(screen.getByRole("button", { name: /collapse line/i }));
    await userEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(screen.queryByLabelText(/manual total/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /restage/i }));
    expect(screen.getByLabelText(/manual total/i)).toBeInTheDocument();
  });

  it("disables the manual checkbox on a line with no engine total to fall back to", () => {
    renderWithProviders(<Harness initial={[noRateLine()]} />);
    // Un-ticking would strand the line permanently invalid (no engine price).
    expect(screen.getByRole("checkbox", { name: /override the price manually/i })).toBeDisabled();
  });

  it("disables the commit actions for a user without the reservations role", () => {
    useAuthStore.setState({ role: "VIEWER", isSuperuser: false, status: "authenticated" });
    renderWithProviders(<Harness initial={[stagedLine()]} />);
    expect(screen.getByRole("button", { name: /save draft/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeDisabled();
  });
});
