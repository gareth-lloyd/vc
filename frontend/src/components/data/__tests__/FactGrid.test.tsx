import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FactGrid, FactGridItem } from "../FactGrid";

describe("FactGrid", () => {
  it("renders each item's label and value", () => {
    render(
      <FactGrid>
        <FactGridItem label="Check-in" value="1 Jul 2026" />
        <FactGridItem label="Nights" value={7} />
      </FactGrid>,
    );
    expect(screen.getByText("Check-in")).toBeInTheDocument();
    expect(screen.getByText("1 Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("Nights")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("applies the three-column layout when requested", () => {
    const { container } = render(
      <FactGrid columns={3}>
        <FactGridItem label="A" value="1" />
      </FactGrid>,
    );
    expect(container.querySelector("dl")).toHaveClass("sm:grid-cols-3");
  });
});
