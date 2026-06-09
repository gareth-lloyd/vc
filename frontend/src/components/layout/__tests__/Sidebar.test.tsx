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
});
