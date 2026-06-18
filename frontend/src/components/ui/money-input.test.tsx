import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MoneyInput } from "./money-input";

describe("MoneyInput", () => {
  it("renders a single-character adornment with pl-9 padding", () => {
    render(<MoneyInput adornment="£" aria-label="amount" />);
    expect(screen.getByText("£")).toBeInTheDocument();
    expect(screen.getByLabelText("amount")).toHaveClass("pl-9");
  });

  it("widens padding to pl-12 for a multi-character adornment", () => {
    render(<MoneyInput adornment="AED" aria-label="amount" />);
    expect(screen.getByText("AED")).toBeInTheDocument();
    const input = screen.getByLabelText("amount");
    expect(input).toHaveClass("pl-12");
    expect(input).not.toHaveClass("pl-9");
  });

  it("renders no adornment span or padding when adornment is null", () => {
    render(<MoneyInput adornment={null} aria-label="amount" />);
    const input = screen.getByLabelText("amount");
    expect(input).not.toHaveClass("pl-9");
    expect(input).not.toHaveClass("pl-12");
  });

  it("keeps the same input element when the adornment toggles (no remount)", () => {
    const { rerender } = render(<MoneyInput adornment={null} aria-label="amount" />);
    const before = screen.getByLabelText("amount");
    rerender(<MoneyInput adornment="£" aria-label="amount" />);
    const after = screen.getByLabelText("amount");
    // A remount would create a new DOM node; a stable element keeps focus/caret.
    expect(after).toBe(before);
    expect(after).toHaveClass("pl-9");
  });
});
