import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { AssignDialog } from "../components/AssignDialog";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const usersFixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 11,
      email: "ada@example.com",
      first_name: "Ada",
      last_name: "Lovelace",
      role: "reservations",
      is_active: true,
    },
    {
      id: 12,
      email: "grace@example.com",
      first_name: "Grace",
      last_name: "Hopper",
      role: "admin",
      is_active: true,
    },
  ],
};

beforeEach(() => {
  server.use(http.get("/api/v1/users", () => HttpResponse.json(usersFixture)));
});

afterEach(() => {
  server.resetHandlers();
});

describe("AssignDialog operator picker", () => {
  it("loads and displays operator options in the list", async () => {
    renderWithProviders(
      <AssignDialog enquiryId={1} currentUserId={null} open onOpenChange={() => {}} />,
    );

    const listbox = await screen.findByRole("listbox", { name: /operator/i });
    expect(within(listbox).getByText(/unassigned/i)).toBeInTheDocument();
    expect(await within(listbox).findByText(/Ada Lovelace/)).toBeInTheDocument();
    expect(within(listbox).getByText(/Grace Hopper/)).toBeInTheDocument();
  });

  it("filters the list via the search input", async () => {
    let lastSearch: string | null = null;
    server.use(
      http.get("/api/v1/users", ({ request }) => {
        const url = new URL(request.url);
        lastSearch = url.searchParams.get("search");
        return HttpResponse.json(usersFixture);
      }),
    );

    renderWithProviders(
      <AssignDialog enquiryId={1} currentUserId={null} open onOpenChange={() => {}} />,
    );

    const search = await screen.findByPlaceholderText(/search operators/i);
    await userEvent.type(search, "ada");
    await waitFor(() => expect(lastSearch).toBe("ada"));
  });

  it("posts the selected user id to :assign on submit", async () => {
    let assignBody: unknown = null;
    server.use(
      http.post("/api/v1/enquiries/1:assign", async ({ request }) => {
        assignBody = await request.json();
        return HttpResponse.json({
          id: 1,
          reference: "E-001",
          status: "new",
          guest: null,
          first_name: "Ada",
          last_name: "Lovelace",
          email: "ada@example.com",
          property: null,
          region: null,
          date_from: null,
          date_to: null,
          adults: 2,
          children: 0,
          request_type: "quote",
          assigned_to: 11,
          agent: null,
          site_source: "main_website",
          created_at: null,
          updated_at: null,
          is_flexible: false,
          min_bedrooms: null,
          referral_code: "",
          inbound_message: "",
        });
      }),
    );

    renderWithProviders(
      <AssignDialog enquiryId={1} currentUserId={null} open onOpenChange={() => {}} />,
    );

    await userEvent.click(await screen.findByRole("option", { name: /Ada Lovelace/ }));

    await userEvent.click(screen.getByRole("button", { name: /^assign$/i }));

    await waitFor(() => expect(assignBody).toEqual({ user: 11 }));
  });

  it("sends user: null when 'Unassigned' is selected", async () => {
    let assignBody: unknown = null;
    server.use(
      http.post("/api/v1/enquiries/2:assign", async ({ request }) => {
        assignBody = await request.json();
        return HttpResponse.json({
          id: 2,
          reference: "E-002",
          status: "new",
          guest: null,
          first_name: "",
          last_name: "",
          email: "",
          property: null,
          region: null,
          date_from: null,
          date_to: null,
          adults: 1,
          children: 0,
          request_type: "quote",
          assigned_to: null,
          agent: null,
          site_source: "main_website",
          created_at: null,
          updated_at: null,
          is_flexible: false,
          min_bedrooms: null,
          referral_code: "",
          inbound_message: "",
        });
      }),
    );

    renderWithProviders(
      <AssignDialog enquiryId={2} currentUserId={11} open onOpenChange={() => {}} />,
    );

    await userEvent.click(await screen.findByRole("option", { name: /unassigned/i }));

    await userEvent.click(screen.getByRole("button", { name: /^assign$/i }));

    await waitFor(() => expect(assignBody).toEqual({ user: null }));
  });

  it("renders an error state when the user fetch fails", async () => {
    server.use(http.get("/api/v1/users", () => HttpResponse.json({}, { status: 500 })));
    renderWithProviders(
      <AssignDialog enquiryId={3} currentUserId={null} open onOpenChange={() => {}} />,
    );
    expect(await screen.findByText(/couldn't load operators/i)).toBeInTheDocument();
  });

  it("shows a no-operators message when the unfiltered list is empty", async () => {
    server.use(
      http.get("/api/v1/users", () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderWithProviders(
      <AssignDialog enquiryId={4} currentUserId={null} open onOpenChange={() => {}} />,
    );
    expect(await screen.findByText(/no operators are available/i)).toBeInTheDocument();
  });

  it("shows an empty-search message when the search returns no operators", async () => {
    server.use(
      http.get("/api/v1/users", ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("search") === "zzz") {
          return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
        }
        return HttpResponse.json(usersFixture);
      }),
    );

    renderWithProviders(
      <AssignDialog enquiryId={5} currentUserId={null} open onOpenChange={() => {}} />,
    );

    await screen.findByText(/Ada Lovelace/);
    await userEvent.type(screen.getByPlaceholderText(/search operators/i), "zzz");
    expect(await screen.findByText(/no operators match that search/i)).toBeInTheDocument();
  });
});
