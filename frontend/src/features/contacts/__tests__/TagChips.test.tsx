import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { TagChips } from "../components/TagChips";

describe("TagChips", () => {
  it("renders the taxonomy label for a known value", () => {
    renderWithProviders(<TagChips tags={["vip"]} />);
    expect(screen.getByText("VIP")).toBeInTheDocument();
  });

  it("falls back to the raw value for an unknown tag", () => {
    renderWithProviders(<TagChips tags={["mystery_tag"]} />);
    expect(screen.getByText("mystery_tag")).toBeInTheDocument();
  });

  it("renders nothing when there are no tags", () => {
    const { container } = renderWithProviders(<TagChips tags={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
