import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatTiles } from "../StatTiles";

describe("StatTiles", () => {
  it("renders a label and value per tile", () => {
    render(
      <StatTiles
        tiles={[
          { label: "Total", value: "£1,000.00" },
          { label: "Paid", value: "£500.00", tone: "success" },
          { label: "Due", value: "£500.00", tone: "warning" },
        ]}
      />,
    );
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("Paid")).toBeInTheDocument();
    expect(screen.getByText("£1,000.00")).toBeInTheDocument();
    expect(screen.getAllByText("£500.00")).toHaveLength(2);
  });

  it("tints the value with the requested tone", () => {
    render(<StatTiles tiles={[{ label: "Due", value: "£500.00", tone: "danger" }]} />);
    expect(screen.getByText("£500.00")).toHaveClass("text-danger");
  });

  it("renders an optional hint", () => {
    render(<StatTiles tiles={[{ label: "Due", value: "£500.00", hint: "by 1 Jul" }]} />);
    expect(screen.getByText("by 1 Jul")).toBeInTheDocument();
  });
});
