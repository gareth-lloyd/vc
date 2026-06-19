import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContactEnquiryHistory } from "../components/ContactEnquiryHistory";

const HISTORY = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      reference: "E-2026-000001",
      status: "converted",
      site_source: "main_website",
      request_type: "quote",
      created_at: "2026-05-01T00:00:00Z",
      quote_count: 3,
      converted_booking: { reference: "VC1234", status: "deposit_paid" },
    },
    {
      id: 2,
      reference: "E-2026-000002",
      status: "quoted",
      site_source: "agent_portal",
      request_type: "quote",
      created_at: "2026-04-01T00:00:00Z",
      quote_count: 1,
      converted_booking: null,
    },
  ],
};

describe("ContactEnquiryHistory", () => {
  it("is collapsed by default and reveals rows on expand", async () => {
    server.use(http.get("/api/v1/contacts/55/enquiries", () => HttpResponse.json(HISTORY)));

    renderWithProviders(<ContactEnquiryHistory contactId={55} />);

    // Header shows the total count once the query resolves.
    expect(await screen.findByText(/enquiry history \(2\)/i)).toBeInTheDocument();
    // Rows are hidden until expanded.
    expect(screen.queryByText("E-2026-000001")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /toggle enquiry history/i }));

    expect(await screen.findByText("E-2026-000001")).toBeInTheDocument();
    expect(screen.getByText("E-2026-000002")).toBeInTheDocument();
  });

  it("renders quote count and the converted booking reference + status", async () => {
    server.use(http.get("/api/v1/contacts/55/enquiries", () => HttpResponse.json(HISTORY)));

    renderWithProviders(<ContactEnquiryHistory contactId={55} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle enquiry history/i }));

    await screen.findByText("E-2026-000001");
    expect(screen.getByText(/3 quotes/i)).toBeInTheDocument();
    expect(screen.getByText("VC1234")).toBeInTheDocument();
    // Converted-booking status uses the real booking-status label, not a literal.
    expect(screen.getByText(/deposit paid/i)).toBeInTheDocument();
    // The unconverted enquiry shows no booking reference.
    expect(screen.getByText(/1 quote\b/i)).toBeInTheDocument();
  });

  it("shows the empty state when the contact has no enquiries", async () => {
    server.use(
      http.get("/api/v1/contacts/77/enquiries", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );

    renderWithProviders(<ContactEnquiryHistory contactId={77} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle enquiry history/i }));

    expect(await screen.findByText(/no previous enquiries/i)).toBeInTheDocument();
  });

  it("surfaces a 'more not shown' hint when the page is truncated", async () => {
    server.use(
      http.get("/api/v1/contacts/55/enquiries", () =>
        HttpResponse.json({
          count: 5,
          next: "http://x/next",
          previous: null,
          results: HISTORY.results,
        }),
      ),
    );

    renderWithProviders(<ContactEnquiryHistory contactId={55} />);
    await userEvent.click(await screen.findByRole("button", { name: /toggle enquiry history/i }));

    await waitFor(() =>
      expect(screen.getByText(/3 more enquiries not shown/i)).toBeInTheDocument(),
    );
  });
});
