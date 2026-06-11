import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../StatusBadge";

describe("StatusBadge", () => {
  it("renders the raw status when no label is given", () => {
    render(<StatusBadge status="draft" />);
    expect(screen.getByText("draft")).toBeInTheDocument();
  });

  it("renders the humanised label while keying the visual kind on the raw status", () => {
    render(<StatusBadge status="deposit_paid" label="Deposit paid" />);
    expect(screen.getByText("Deposit paid")).toBeInTheDocument();
    expect(screen.queryByText("deposit_paid")).not.toBeInTheDocument();
    // kind mapping still resolves from the raw status (active → success icon).
    expect(screen.getByText("Deposit paid").parentElement).toHaveClass("text-success");
  });
});
