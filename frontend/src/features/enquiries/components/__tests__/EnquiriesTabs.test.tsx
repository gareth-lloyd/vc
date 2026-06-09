import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { EnquiriesTabs } from "../EnquiriesTabs";

describe("EnquiriesTabs", () => {
  it("marks Enquiries active on /enquiries, not Quotes", () => {
    renderWithProviders(<EnquiriesTabs />, { route: "/enquiries" });
    expect(screen.getByRole("link", { name: "Enquiries" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Quotes" })).not.toHaveAttribute("aria-current");
  });

  it("marks Quotes active on /enquiries/quotes — Enquiries stays inactive (end match)", () => {
    renderWithProviders(<EnquiriesTabs />, { route: "/enquiries/quotes" });
    expect(screen.getByRole("link", { name: "Quotes" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Enquiries" })).not.toHaveAttribute("aria-current");
  });

  it("links each tab to its route", () => {
    renderWithProviders(<EnquiriesTabs />, { route: "/enquiries" });
    expect(screen.getByRole("link", { name: "Enquiries" })).toHaveAttribute("href", "/enquiries");
    expect(screen.getByRole("link", { name: "Quotes" })).toHaveAttribute(
      "href",
      "/enquiries/quotes",
    );
  });
});
