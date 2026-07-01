import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TwoColumn } from "../TwoColumn";

describe("TwoColumn", () => {
  it("shows the rail from the lg breakpoint by default (unchanged for existing callers)", () => {
    render(
      <TwoColumn rightRail={<span>rail-content</span>}>
        <span>main-content</span>
      </TwoColumn>,
    );
    const aside = screen.getByRole("complementary");
    expect(aside).toHaveClass("hidden", "lg:block");
    expect(screen.getByText("rail-content")).toBeInTheDocument();
  });

  it("hides the rail at every width when hideRail is set (full-width main)", () => {
    render(
      <TwoColumn hideRail rightRail={<span>rail-content</span>}>
        <span>main-content</span>
      </TwoColumn>,
    );
    const aside = screen.getByRole("complementary");
    // display:none at every breakpoint — no `lg:block` escape hatch.
    expect(aside).toHaveClass("hidden");
    expect(aside).not.toHaveClass("lg:block");
    // Still mounted so its subtree state survives (hide, not unmount).
    expect(screen.getByText("rail-content")).toBeInTheDocument();
  });
});
