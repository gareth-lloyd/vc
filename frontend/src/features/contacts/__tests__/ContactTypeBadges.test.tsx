import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { ContactTypeBadges } from "../components/ContactTypeBadges";

describe("ContactTypeBadges", () => {
  it("renders a translated badge per type", () => {
    renderWithProviders(<ContactTypeBadges types={["customer", "owner"]} />);
    expect(screen.getByText("Customer")).toBeInTheDocument();
    expect(screen.getByText("Owner")).toBeInTheDocument();
  });

  it("falls back to the raw value for an unknown type", () => {
    renderWithProviders(<ContactTypeBadges types={["mystery_role"]} />);
    expect(screen.getByText("mystery_role")).toBeInTheDocument();
  });

  it("renders larger accent-filled chips in prominent mode", () => {
    renderWithProviders(<ContactTypeBadges types={["owner"]} prominent />);
    const badge = screen.getByText("Owner");
    expect(badge).toHaveClass("text-sm");
    expect(badge).toHaveStyle({ backgroundColor: "var(--accent-700)" });
  });

  it("renders nothing when there are no types", () => {
    const { container } = renderWithProviders(<ContactTypeBadges types={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
