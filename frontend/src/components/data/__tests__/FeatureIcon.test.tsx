import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { FeatureIcon } from "../FeatureIcon";

vi.mock("lucide-react/dynamic", () => ({
  iconNames: ["wifi", "waves", "flame"],
  DynamicIcon: ({ name, className }: { name: string; className?: string }) => (
    <svg data-testid={`dyn-${name}`} className={className} />
  ),
}));

describe("FeatureIcon", () => {
  it("renders the named lucide icon when the name is valid", () => {
    const { getByTestId } = render(<FeatureIcon name="wifi" />);
    expect(getByTestId("dyn-wifi")).toBeInTheDocument();
  });

  it("renders the fallback for an empty name", () => {
    const { queryByTestId, container } = render(<FeatureIcon name="" />);
    expect(queryByTestId(/^dyn-/)).toBeNull();
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders the fallback for an unknown name (no throw)", () => {
    const { queryByTestId, container } = render(<FeatureIcon name="not-a-real-icon" />);
    expect(queryByTestId(/^dyn-/)).toBeNull();
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders nothing when fallback is null and the name is invalid", () => {
    const { container } = render(<FeatureIcon name={null} fallback={null} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
