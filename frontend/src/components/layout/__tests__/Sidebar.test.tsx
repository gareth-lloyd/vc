import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { Sidebar } from "../Sidebar";

describe("Sidebar", () => {
  it("keeps Quotes and Enquiries but has no standalone Quotes item (folded into the Enquiries tab)", () => {
    renderWithProviders(<Sidebar />, { route: "/enquiries" });
    expect(screen.getByRole("link", { name: "Quotes and Enquiries" })).toHaveAttribute(
      "href",
      "/enquiries",
    );
    expect(screen.queryByRole("link", { name: "Quotes" })).not.toBeInTheDocument();
  });

  it("keeps Quotes and Enquiries highlighted on a nested quote-detail route", () => {
    // Quote detail lives at /enquiries/quotes/:id, so the prefix-matching
    // nav item stays active — no orphaned, unhighlighted page.
    renderWithProviders(<Sidebar />, { route: "/enquiries/quotes/50" });
    expect(screen.getByRole("link", { name: "Quotes and Enquiries" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("orders the main section with Concierge moved to an Experiments section at the bottom", () => {
    renderWithProviders(<Sidebar />, { route: "/dashboard" });
    const labels = screen.getAllByRole("link").map((link) => link.textContent);
    expect(labels).toEqual([
      "Dashboard",
      "Properties",
      "Availability",
      "Contacts",
      "Bookings",
      "Quotes and Enquiries",
      "Owner blocks",
      "Concierge",
    ]);
    expect(screen.getByRole("heading", { name: "Experiments" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Library" })).not.toBeInTheDocument();
  });
});
