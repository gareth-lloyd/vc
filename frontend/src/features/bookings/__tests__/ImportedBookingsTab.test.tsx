import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { formatDateRangeEndpoints } from "@/lib/format/date";
import { ImportedBookingsTab } from "../components/ImportedBookingsTab";

const base = {
  id: 1,
  booking_number: "",
  villa_name: "Villa Yeraki",
  property: null,
  property_name: null,
  destination: "",
  year: 2019,
  notes: "",
  date_from: null,
  date_to: null,
  amount: null,
  currency_code: null,
  person: 7,
  person_name: "Ada Lovelace",
};

const ROWS = [
  {
    ...base,
    id: 1,
    booking_number: "BN500",
    villa_name: "Test Villa (sheet)",
    property: 12,
    property_name: "Test Villa",
    destination: "Corfu",
    year: 2025,
    date_from: "2025-08-03",
    date_to: "2025-08-10",
    amount: "4250.00",
    currency_code: "GBP",
  },
  { ...base, id: 2, person: 8, person_name: "Grace Hopper", villa_name: "Villa Unknown" },
  { ...base, id: 3, person: 9, person_name: null, year: null, amount: "900.00" },
];

const PAST_STAYS = "/api/v1/past-stays";

function renderTab(route = "/bookings?tab=imported") {
  return renderWithProviders(<ImportedBookingsTab />, { route });
}

function rowFor(text: string): HTMLElement {
  const row = screen.getByText(text).closest("tr");
  if (!row) throw new Error(`no row for ${text}`);
  return row;
}

describe("ImportedBookingsTab", () => {
  it("renders guest and villa links, dates or year, and the recorded amount", async () => {
    server.use(http.get(PAST_STAYS, () => HttpResponse.json(drfPage(ROWS))));
    renderTab();

    const guest = await screen.findByRole("link", { name: "Ada Lovelace" });
    expect(guest).toHaveAttribute("href", "/clients/7/details");
    expect(screen.getByRole("link", { name: "Test Villa" })).toHaveAttribute(
      "href",
      "/properties/12",
    );
    const dated = rowFor("Ada Lovelace");
    expect(
      within(dated).getByText(formatDateRangeEndpoints("2025-08-03", "2025-08-10")),
    ).toBeInTheDocument();
    expect(within(dated).getByText("Corfu")).toBeInTheDocument();
    expect(within(dated).getByText("BN500")).toBeInTheDocument();
    expect(within(dated).getByText("£4,250.00")).toBeInTheDocument();

    // Unmatched villa: the sheet's raw name, not a link.
    const unlinked = rowFor("Grace Hopper");
    expect(within(unlinked).getByText("Villa Unknown")).toBeInTheDocument();
    expect(within(unlinked).queryByRole("link", { name: "Villa Unknown" })).toBeNull();
    expect(within(unlinked).getByText("2019")).toBeInTheDocument();
  });

  it("labels a nameless guest and an unknown year, and shows a currency-less amount bare", async () => {
    server.use(http.get(PAST_STAYS, () => HttpResponse.json(drfPage(ROWS))));
    renderTab();

    const guest = await screen.findByRole("link", { name: "Unnamed client" });
    expect(guest).toHaveAttribute("href", "/clients/9/details");
    const row = rowFor("Unnamed client");
    expect(within(row).getByText("Year unknown")).toBeInTheDocument();
    expect(within(row).getByText("900.00")).toBeInTheDocument();
  });

  it("requests the page from the URL and pages forward", async () => {
    const pages: (string | null)[] = [];
    server.use(
      http.get(PAST_STAYS, ({ request }) => {
        pages.push(new URL(request.url).searchParams.get("page"));
        return HttpResponse.json(drfPage(ROWS, { count: 120, next: "x" }));
      }),
    );
    renderTab();

    await screen.findByText("Grace Hopper");
    await userEvent.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => expect(pages).toContain("2"));
    expect(pages[0]).toBeNull();
  });

  it("sends the search box as ?search=", async () => {
    const searches: (string | null)[] = [];
    server.use(
      http.get(PAST_STAYS, ({ request }) => {
        searches.push(new URL(request.url).searchParams.get("search"));
        return HttpResponse.json(drfPage(ROWS));
      }),
    );
    renderTab();

    await screen.findByText("Grace Hopper");
    await userEvent.type(screen.getByRole("searchbox"), "Hopper");

    await waitFor(() => expect(searches).toContain("Hopper"));
  });

  it("shows the empty state", async () => {
    server.use(http.get(PAST_STAYS, () => HttpResponse.json(drfPage([]))));
    renderTab();

    expect(await screen.findByText("No imported bookings found")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    let calls = 0;
    server.use(
      http.get(PAST_STAYS, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: "boom" }, { status: 500 })
          : HttpResponse.json(drfPage(ROWS));
      }),
    );
    renderTab();

    expect(await screen.findByText("Couldn't load imported bookings.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Grace Hopper")).toBeInTheDocument();
  });
});
