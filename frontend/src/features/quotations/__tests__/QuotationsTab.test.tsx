import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { EnquiriesSectionLayout } from "@/features/enquiries/EnquiriesSectionLayout";
import { QuotationsTab } from "../QuotationsTab";

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      reference: "Q-2026-001",
      status: "draft",
      guest: 42,
      created_at: "2026-05-01T10:00:00Z",
    },
    {
      id: 2,
      reference: "Q-2026-002",
      status: "sent",
      guest: null,
      created_at: "2026-05-02T10:00:00Z",
    },
  ],
};

function setup(extra?: React.ReactNode) {
  return renderWithProviders(
    <Routes>
      {/* Mount under the section layout so the tab strip renders, as in prod. */}
      <Route path="/enquiries" element={<EnquiriesSectionLayout />}>
        <Route path="quotes" element={<QuotationsTab />} />
      </Route>
      {extra}
    </Routes>,
    { route: "/enquiries/quotes" },
  );
}

describe("QuotationsTab (/enquiries/quotes)", () => {
  it("renders quote rows from /quotations", async () => {
    server.use(http.get("/api/v1/quotations", () => HttpResponse.json(fixture)));
    setup();
    expect(await screen.findByText("Q-2026-001")).toBeInTheDocument();
    expect(screen.getByText("Q-2026-002")).toBeInTheDocument();
  });

  it("renders the empty state when no rows", async () => {
    server.use(
      http.get("/api/v1/quotations", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    setup();
    expect(await screen.findByText(/no quotations match/i)).toBeInTheDocument();
  });

  it("navigates to the quote detail on row click", async () => {
    server.use(http.get("/api/v1/quotations", () => HttpResponse.json(fixture)));
    setup(<Route path="/enquiries/quotes/:id" element={<div>Detail page</div>} />);
    await userEvent.click(await screen.findByText("Q-2026-001"));
    expect(await screen.findByText("Detail page")).toBeInTheDocument();
  });

  it("does not render a 'new quote' button — creation now lives in the enquiry workspace", async () => {
    server.use(http.get("/api/v1/quotations", () => HttpResponse.json(fixture)));
    setup();
    await screen.findByText("Q-2026-001");
    expect(screen.queryByRole("button", { name: /new quote/i })).not.toBeInTheDocument();
  });

  it("shows the Enquiries↔Quotes tab strip with Quotes active", async () => {
    server.use(http.get("/api/v1/quotations", () => HttpResponse.json(fixture)));
    setup();
    await screen.findByText("Q-2026-001");
    expect(screen.getByRole("link", { name: "Quotes" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Enquiries" })).toHaveAttribute("href", "/enquiries");
  });
});
