import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import { EnquiriesSectionLayout } from "../EnquiriesSectionLayout";

function setup(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/enquiries" element={<EnquiriesSectionLayout />}>
        <Route index element={<div>List child</div>} />
        <Route path="quotes" element={<div>Quotes child</div>} />
      </Route>
    </Routes>,
    { route },
  );
}

describe("EnquiriesSectionLayout", () => {
  it("renders the tab strip once around the active child", () => {
    setup("/enquiries");
    expect(screen.getByRole("link", { name: "Enquiries" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quotes" })).toBeInTheDocument();
    expect(screen.getByText("List child")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Enquiries" })).toHaveAttribute("aria-current", "page");
  });

  it("swaps the child and active tab on the quotes route", () => {
    setup("/enquiries/quotes");
    expect(screen.getByText("Quotes child")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quotes" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Enquiries" })).not.toHaveAttribute("aria-current");
  });
});
