import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Collapsible } from "../collapsible";

describe("Collapsible", () => {
  it("keeps the body unmounted until toggled open", async () => {
    render(
      <Collapsible title="Activity">
        <p>timeline body</p>
      </Collapsible>,
    );
    // Body absent (not just hidden) while collapsed — data hooks inside stay dormant.
    expect(screen.queryByText("timeline body")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Activity" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);
    expect(screen.getByText("timeline body")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("honours defaultOpen and uses toggleAriaLabel for the accessible name", () => {
    render(
      <Collapsible title={<span>x</span>} defaultOpen toggleAriaLabel="Toggle history">
        <p>body</p>
      </Collapsible>,
    );
    expect(screen.getByText("body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Toggle history" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
