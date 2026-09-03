import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactPastStayHistory } from "../components/ContactPastStayHistory";

const STAYS = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      booking_number: "BN123",
      villa_name: "Yeraki",
      property: 10,
      property_name: "Villa Yeraki",
      destination: "Corfu",
      year: 2023,
      notes: "",
    },
    {
      id: 2,
      booking_number: "",
      villa_name: "Casa Nowhere",
      property: null,
      property_name: null,
      destination: "",
      year: null,
      notes: "CANCELLED",
    },
  ],
};

describe("ContactPastStayHistory", () => {
  it("is collapsed by default and reveals stay rows on expand", async () => {
    server.use(http.get("/api/v1/contacts/55/past-stays", () => HttpResponse.json(STAYS)));

    renderWithProviders(<ContactPastStayHistory contactId={55} />);

    expect(await screen.findByText(/past stays \(2\)/i)).toBeInTheDocument();
    expect(screen.queryByText("Villa Yeraki")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /toggle past stays/i }));

    // A linked stay shows the resolved property name (as a link) + destination.
    expect(await screen.findByRole("link", { name: "Villa Yeraki" })).toHaveAttribute(
      "href",
      "/properties/10",
    );
    expect(screen.getByText("Corfu")).toBeInTheDocument();
    expect(screen.getByText(/2023 · BN123/)).toBeInTheDocument();
    // An unlinked stay falls back to the sheet's villa text and "Year unknown".
    expect(screen.getByText("Casa Nowhere")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Casa Nowhere" })).not.toBeInTheDocument();
    expect(screen.getByText(/year unknown/i)).toBeInTheDocument();
  });

  it("shows the empty state when the contact has no past stays", async () => {
    server.use(
      http.get("/api/v1/contacts/77/past-stays", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );

    renderWithProviders(<ContactPastStayHistory contactId={77} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle past stays/i }));

    expect(await screen.findByText(/no past stays on record/i)).toBeInTheDocument();
  });

  it("surfaces a 'more not shown' hint when the page is truncated", async () => {
    server.use(
      http.get("/api/v1/contacts/55/past-stays", () =>
        HttpResponse.json({
          count: 5,
          next: "http://x/next",
          previous: null,
          results: STAYS.results,
        }),
      ),
    );

    renderWithProviders(<ContactPastStayHistory contactId={55} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle past stays/i }));

    await waitFor(() =>
      expect(screen.getByText(/3 more past stays not shown/i)).toBeInTheDocument(),
    );
  });
});
