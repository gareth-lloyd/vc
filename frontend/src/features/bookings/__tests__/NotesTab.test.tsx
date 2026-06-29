import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { NotesTab } from "../tabs/NotesTab";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

const bookingFixture = {
  id: BOOKING_ID,
  reference: "B-AAA-001",
  status: "deposit_paid",
  property: 12,
  agent: null,
  assigned_to: null,
  date_from: "2026-07-01",
  date_to: "2026-07-08",
  adults: 2,
  children: 1,
  currency: 1,
  rental_price: "1500.00",
  balance_due: "1000.00",
  balance_due_at: "2026-06-01",
  site_source: "main_website",
  is_archived: false,
  archived_at: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
  property_name: "Casa Norte",
  guest_name: "Ada Lovelace",
  guest_email: "ada@example.com",
  currency_code: "GBP",
  total: "2500.00",
  night_count: 7,
  pricing_snapshot: {},
  discount: "0.00",
  adjustment: "0.00",
  terms_version: 1,
  terms_accepted_at: "2026-05-01T00:00:00Z",
  payment_method: "card",
  cancel_reason: "",
  cancelled_at: null,
};

interface NoteFixture {
  id: number;
  booking: number;
  author: number | null;
  kind: "general" | "internal" | "concierge" | "villa";
  body: string;
  is_pinned: boolean;
  visibility: "staff_only" | "owner" | "guest";
  created_at: string;
  updated_at: string;
}

function note(overrides: Partial<NoteFixture> = {}): NoteFixture {
  return {
    id: 1,
    booking: BOOKING_ID,
    author: 1,
    kind: "general",
    body: "hello",
    is_pinned: false,
    visibility: "staff_only",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function notesResponse(items: NoteFixture[]) {
  return { count: items.length, next: null, previous: null, results: items };
}

function setup(route = `/bookings/${BOOKING_ID}/notes`) {
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<BookingDetailLayout />}>
        <Route index element={<Navigate to="notes" replace />} />
        <Route path="notes" element={<NotesTab />} />
      </Route>
    </Routes>,
    { route },
  );
}

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
  server.use(http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture)));
});

afterEach(() => {
  server.resetHandlers();
});

describe("NotesTab", () => {
  it("renders an empty state when there are no notes", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () => HttpResponse.json(notesResponse([]))),
    );
    setup();
    expect(await screen.findByText(/no notes yet/i)).toBeInTheDocument();
  });

  it("orders pinned notes before non-pinned notes regardless of created_at", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () =>
        HttpResponse.json(
          notesResponse([
            note({
              id: 1,
              body: "early non-pinned",
              created_at: "2026-05-01T00:00:00Z",
            }),
            note({
              id: 2,
              body: "late pinned",
              is_pinned: true,
              created_at: "2026-05-10T00:00:00Z",
            }),
          ]),
        ),
      ),
    );
    setup();
    const items = await screen.findAllByRole("listitem");
    expect(within(items[0]).getByText("late pinned")).toBeInTheDocument();
    expect(within(items[1]).getByText("early non-pinned")).toBeInTheDocument();
  });

  it("filters the list when a kind is selected", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () =>
        HttpResponse.json(
          notesResponse([
            note({ id: 1, body: "general body", kind: "general" }),
            note({ id: 2, body: "concierge body", kind: "concierge" }),
          ]),
        ),
      ),
    );
    setup();
    expect(await screen.findByText("general body")).toBeInTheDocument();
    expect(screen.getByText("concierge body")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("combobox", { name: /filter by kind/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Concierge" }));

    await waitFor(() => expect(screen.queryByText("general body")).not.toBeInTheDocument());
    expect(screen.getByText("concierge body")).toBeInTheDocument();
  });

  it("validates empty body in the create dialog without calling the API", async () => {
    let postCalls = 0;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () => HttpResponse.json(notesResponse([]))),
      http.post(`/api/v1/bookings/${BOOKING_ID}/notes`, () => {
        postCalls += 1;
        return HttpResponse.json(note(), { status: 201 });
      }),
    );
    setup();
    await screen.findByText(/no notes yet/i);
    await userEvent.click(screen.getByRole("button", { name: /add note/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Add note" }));
    expect(await screen.findByText(/body is required/i)).toBeInTheDocument();
    expect(postCalls).toBe(0);
  });

  it("creates a note: POSTs, refetches, toast.success, closes dialog", async () => {
    let postCalls = 0;
    let listCalls = 0;
    const stored: NoteFixture[] = [];
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () => {
        listCalls += 1;
        return HttpResponse.json(notesResponse(stored));
      }),
      http.post(`/api/v1/bookings/${BOOKING_ID}/notes`, async ({ request }) => {
        postCalls += 1;
        const body = (await request.json()) as { body: string };
        const created = note({ id: 42, body: body.body });
        stored.push(created);
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    setup();
    await screen.findByText(/no notes yet/i);

    await userEvent.click(screen.getByRole("button", { name: /add note/i }));
    const textarea = await screen.findByLabelText(/body/i);
    await userEvent.type(textarea, "Owner wants a 14:00 pickup");
    await userEvent.click(screen.getByRole("button", { name: "Add note" }));

    await waitFor(() => expect(postCalls).toBe(1));
    expect(await screen.findByText("Owner wants a 14:00 pickup")).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Add note" })).not.toBeInTheDocument();
    expect(listCalls).toBeGreaterThanOrEqual(2);
  });

  it("surfaces backend field_errors in the form, no toast", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () => HttpResponse.json(notesResponse([]))),
      http.post(`/api/v1/bookings/${BOOKING_ID}/notes`, () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Invalid input.",
            field_errors: { body: ["Body too short."] },
          },
          { status: 400 },
        ),
      ),
    );
    setup();
    await screen.findByText(/no notes yet/i);
    await userEvent.click(screen.getByRole("button", { name: /add note/i }));
    const textarea = await screen.findByLabelText(/body/i);
    await userEvent.type(textarea, "x");
    await userEvent.click(screen.getByRole("button", { name: "Add note" }));

    expect(await screen.findByText(/body too short/i)).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("edits an existing note (PATCH with prefilled values)", async () => {
    let patchBody: unknown = null;
    const stored: NoteFixture[] = [note({ id: 5, body: "original body" })];
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () =>
        HttpResponse.json(notesResponse(stored)),
      ),
      http.patch(`/api/v1/bookings/${BOOKING_ID}/notes/5`, async ({ request }) => {
        patchBody = await request.json();
        const updated = { ...stored[0], body: "edited body" };
        stored[0] = updated;
        return HttpResponse.json(updated);
      }),
    );
    setup();
    await screen.findByText("original body");

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const textarea = await screen.findByLabelText(/body/i);
    expect(textarea).toHaveValue("original body");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "edited body");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(patchBody).toMatchObject({ body: "edited body" }));
    expect(await screen.findByText("edited body")).toBeInTheDocument();
  });

  it("deletes a note via the confirm dialog", async () => {
    const stored: NoteFixture[] = [note({ id: 9, body: "to be deleted" })];
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () =>
        HttpResponse.json(notesResponse(stored)),
      ),
      http.delete(`/api/v1/bookings/${BOOKING_ID}/notes/9`, () => {
        stored.length = 0;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    setup();
    await screen.findByText("to be deleted");

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.queryByText("to be deleted")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalled();
  });

  it("optimistically toggles pin and rolls back on 500", async () => {
    let patchCalls = 0;
    const stored: NoteFixture[] = [note({ id: 11, body: "pin me", is_pinned: false })];
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/notes`, () =>
        HttpResponse.json(notesResponse(stored)),
      ),
      http.patch(`/api/v1/bookings/${BOOKING_ID}/notes/11`, () => {
        patchCalls += 1;
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    setup();
    await screen.findByText("pin me");

    const pinBtn = screen.getByRole("button", { name: /^pin note$/i });
    expect(pinBtn).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(pinBtn);

    await waitFor(() => expect(patchCalls).toBe(1));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /pin note/i })).toHaveAttribute(
        "aria-pressed",
        "false",
      ),
    );
    expect(toast.error).toHaveBeenCalled();
  });
});
