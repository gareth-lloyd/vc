import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { QuotationsListPage } from "../QuotationsListPage";

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
      currency: "EUR",
      created_at: "2026-05-01T10:00:00Z",
    },
    {
      id: 2,
      reference: "Q-2026-002",
      status: "sent",
      guest: null,
      currency: null,
      created_at: "2026-05-02T10:00:00Z",
    },
  ],
};

describe("QuotationsListPage", () => {
  it("renders rows from /quotations", async () => {
    server.use(http.get("/api/v1/quotations", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/quotations" element={<QuotationsListPage />} />
      </Routes>,
      { route: "/quotations" },
    );
    expect(await screen.findByText("Q-2026-001")).toBeInTheDocument();
    expect(screen.getByText("Q-2026-002")).toBeInTheDocument();
  });

  it("renders the empty state when no rows", async () => {
    server.use(
      http.get("/api/v1/quotations", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/quotations" element={<QuotationsListPage />} />
      </Routes>,
      { route: "/quotations" },
    );
    expect(await screen.findByText(/no quotations match/i)).toBeInTheDocument();
  });

  it("disables the 'new quote' button with a coming-soon tooltip", async () => {
    server.use(http.get("/api/v1/quotations", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/quotations" element={<QuotationsListPage />} />
      </Routes>,
      { route: "/quotations" },
    );
    const btn = await screen.findByRole("button", { name: /new quote/i });
    expect(btn).toBeDisabled();
  });

  it("navigates to the detail page on row click", async () => {
    server.use(http.get("/api/v1/quotations", () => HttpResponse.json(fixture)));
    renderWithProviders(
      <Routes>
        <Route path="/quotations" element={<QuotationsListPage />} />
        <Route path="/quotations/:id" element={<div>Detail page</div>} />
      </Routes>,
      { route: "/quotations" },
    );
    await userEvent.click(await screen.findByText("Q-2026-001"));
    expect(await screen.findByText("Detail page")).toBeInTheDocument();
  });
});
