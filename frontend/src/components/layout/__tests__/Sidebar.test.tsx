import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { Sidebar } from "../Sidebar";

describe("Sidebar", () => {
  it("keeps Enquiries but has no standalone Quotes item (folded into the Enquiries tab)", () => {
    renderWithProviders(<Sidebar />, { route: "/enquiries" });
    expect(screen.getByRole("link", { name: "Enquiries" })).toHaveAttribute("href", "/enquiries");
    expect(screen.queryByRole("link", { name: "Quotes" })).not.toBeInTheDocument();
  });

  it("keeps Enquiries highlighted on a nested quote-detail route", () => {
    // Quote detail lives at /enquiries/quotes/:id, so the prefix-matching
    // Enquiries nav item stays active — no orphaned, unhighlighted page.
    renderWithProviders(<Sidebar />, { route: "/enquiries/quotes/50" });
    expect(screen.getByRole("link", { name: "Enquiries" })).toHaveAttribute("aria-current", "page");
  });
});
