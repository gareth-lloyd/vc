import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { BookingDetailLayout } from "../BookingDetailLayout";
import { DocumentsTab } from "../tabs/DocumentsTab";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;
const DOCUMENTS_URL = `/api/v1/bookings/${BOOKING_ID}/documents`;

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
  terms_version: 1,
  terms_accepted_at: "2026-05-01T00:00:00Z",
  payment_method: "card",
  cancel_reason: "",
  cancelled_at: null,
  has_been_confirmed: true,
};

interface DocumentFixture {
  id: number;
  kind: string;
  filename: string;
  size: number | null;
  generated_at: string;
  generated_by: { id: number; name: string } | null;
  sent_to_guest_at: string | null;
}

function doc(overrides: Partial<DocumentFixture> = {}): DocumentFixture {
  return {
    id: 9,
    kind: "contract",
    filename: "B-AAA-001-contract-9.pdf",
    size: 4096,
    generated_at: "2026-05-03T09:00:00Z",
    generated_by: { id: 1, name: "Ada Ops" },
    sent_to_guest_at: null,
    ...overrides,
  };
}

function documentsResponse(items: DocumentFixture[]) {
  return { count: items.length, next: null, previous: null, results: items };
}

function listHandler(items: DocumentFixture[]) {
  return http.get(DOCUMENTS_URL, () => HttpResponse.json(documentsResponse(items)));
}

function asReservationsUser() {
  const me: UserMe = {
    id: 1,
    email: "u@v.com",
    first_name: "U",
    last_name: "V",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: "en",
  };
  useAuthStore.getState().setMe(me, { role: "RESERVATIONS", is_superuser: false, permissions: [] });
}

function asViewer() {
  const me: UserMe = {
    id: 2,
    email: "v@v.com",
    first_name: "V",
    last_name: "Iewer",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: "en",
  };
  useAuthStore.getState().setMe(me, { role: "VIEWER", is_superuser: false, permissions: [] });
}

function setup(route = `/bookings/${BOOKING_ID}/documents`) {
  return renderWithProviders(
    <Routes>
      <Route path="/bookings/:id" element={<BookingDetailLayout />}>
        <Route index element={<Navigate to="documents" replace />} />
        <Route path="documents" element={<DocumentsTab />} />
      </Route>
    </Routes>,
    { route },
  );
}

// jsdom implements no object-URL support at all, so these can't be spied —
// they're assigned onto the real `URL` and restored by hand, since neither
// `restoreAllMocks` nor `stubGlobal` would put the constructor back (both
// would leave the mutation in place for every later test in the file).
const originalCreateObjectURL = globalThis.URL.createObjectURL;
const originalRevokeObjectURL = globalThis.URL.revokeObjectURL;

beforeEach(() => {
  asReservationsUser();
  server.use(http.get(`/api/v1/bookings/${BOOKING_ID}`, () => HttpResponse.json(bookingFixture)));
});

afterEach(() => {
  server.resetHandlers();
  useAuthStore.getState().clear();
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
  vi.restoreAllMocks();
  globalThis.URL.createObjectURL = originalCreateObjectURL;
  globalThis.URL.revokeObjectURL = originalRevokeObjectURL;
});

describe("DocumentsTab", () => {
  it("renders a row per document with who generated it and whether it was sent", async () => {
    server.use(
      listHandler([
        doc({ id: 9, sent_to_guest_at: null }),
        doc({
          id: 8,
          filename: "B-AAA-001-contract-8.pdf",
          generated_by: null,
          sent_to_guest_at: "2026-05-02T10:00:00Z",
        }),
      ]),
    );
    setup();

    expect(await screen.findByText("B-AAA-001-contract-9.pdf")).toBeInTheDocument();
    expect(screen.getByText("B-AAA-001-contract-8.pdf")).toBeInTheDocument();
    expect(screen.getByText(/ada ops/i)).toBeInTheDocument();
    // A document minted by the auto-generation path has no request user
    // behind it — the tab has to say "the system did this", not blank.
    expect(screen.getByText(/system/i)).toBeInTheDocument();
    expect(screen.getByText(/not sent/i)).toBeInTheDocument();
    // A contract is on file, so no missing-contract warning.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders a neutral empty state when a draft booking has no documents", async () => {
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json({ ...bookingFixture, status: "draft", has_been_confirmed: false }),
      ),
      listHandler([]),
    );
    setup();
    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/no contract on file/i)).not.toBeInTheDocument();
    // Generating would only buy a 409 — the backend refuses a never-confirmed booking.
    expect(screen.getByRole("button", { name: /generate contract/i })).toBeDisabled();
  });

  it("warns when a confirmed booking has no contract", async () => {
    // The fixture has been confirmed, so the auto-generated contract should
    // exist. Its absence is the one staff-visible sign that
    // `auto_generate_contract` failed silently.
    server.use(listHandler([]));
    setup();
    expect(await screen.findByRole("status")).toHaveTextContent(/no contract on file/i);
    expect(screen.queryByText(/no documents yet/i)).not.toBeInTheDocument();
  });

  it("still warns when a confirmed booking's only document is not a contract", async () => {
    server.use(listHandler([doc({ kind: "invoice", filename: "B-AAA-001-invoice-9.pdf" })]));
    setup();
    expect(await screen.findByText("B-AAA-001-invoice-9.pdf")).toBeInTheDocument();
    expect(screen.getByText(/no contract on file/i)).toBeInTheDocument();
  });

  it("posts to :generate and refreshes the list", async () => {
    let generated: unknown = null;
    let listCalls = 0;
    server.use(
      http.get(DOCUMENTS_URL, () => {
        listCalls += 1;
        return HttpResponse.json(documentsResponse(listCalls === 1 ? [] : [doc()]));
      }),
      http.post(`${DOCUMENTS_URL}:generate`, async ({ request }) => {
        generated = await request.json();
        return HttpResponse.json(doc(), { status: 201 });
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /generate contract/i }));

    await waitFor(() => expect(generated).toEqual({ kind: "contract" }));
    expect(await screen.findByText("B-AAA-001-contract-9.pdf")).toBeInTheDocument();
    expect(vi.mocked(toast.success)).toHaveBeenCalled();
  });

  it("confirms before sending, then posts to :send", async () => {
    let sendCalled = false;
    server.use(
      listHandler([doc()]),
      http.post(`${DOCUMENTS_URL}/9:send`, () => {
        sendCalled = true;
        return HttpResponse.json(doc({ sent_to_guest_at: "2026-05-04T08:00:00Z" }));
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /send to guest/i }));
    // The guest's address belongs in the confirmation, not in a toast after
    // the mail has gone: it is the one thing an operator can still catch.
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/ada@example\.com/)).toBeInTheDocument();
    expect(sendCalled).toBe(false);

    await userEvent.click(within(dialog).getByRole("button", { name: /send/i }));

    await waitFor(() => expect(sendCalled).toBe(true));
    expect(vi.mocked(toast.success)).toHaveBeenCalled();
  });

  it("shows the server's reason when a send never reaches the mail pipeline", async () => {
    server.use(
      listHandler([doc()]),
      http.post(`${DOCUMENTS_URL}/9:send`, () =>
        HttpResponse.json(
          {
            code: "document_send_failed",
            detail: "Document 9 could not be emailed; see the booking's email log.",
            field_errors: {},
          },
          { status: 409 },
        ),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /send to guest/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /send/i }));

    await waitFor(() =>
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
        expect.stringContaining("could not be emailed"),
      ),
    );
  });

  it("downloads through the blob endpoint and clicks an object-URL anchor", async () => {
    const objectUrl = "blob:mock-url";
    const createObjectURL = vi.fn(() => objectUrl);
    const revokeObjectURL = vi.fn();
    globalThis.URL.createObjectURL = createObjectURL;
    globalThis.URL.revokeObjectURL = revokeObjectURL;
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this);
    });

    server.use(
      listHandler([doc()]),
      http.get(`${DOCUMENTS_URL}/9:download`, () =>
        HttpResponse.arrayBuffer(new TextEncoder().encode("%PDF-1.7\n").buffer as ArrayBuffer, {
          headers: {
            "content-type": "application/pdf",
            "content-disposition": 'attachment; filename="B-AAA-001-contract-9.pdf"',
          },
        }),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /download/i }));

    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clicked[0].href).toContain(objectUrl);
    // The filename comes off `Content-Disposition`, not the list row: the
    // download is the one place the server's own name for the bytes is
    // authoritative.
    expect(clicked[0].download).toBe("B-AAA-001-contract-9.pdf");
    // Deferred a task past the click — Firefox and Safari can kill the blob
    // entry out from under a download revoked in the same task.
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith(objectUrl));
  });

  it("previews the contract HTML in a sandboxed iframe", async () => {
    server.use(
      listHandler([doc()]),
      http.get(`/api/v1/bookings/${BOOKING_ID}/documents:preview`, () =>
        HttpResponse.json({ html: "<p>House rules snapshot</p>" }),
      ),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /preview/i }));

    const dialog = await screen.findByRole("dialog");
    const iframe = await within(dialog).findByTitle(/contract preview/i);
    expect(iframe).toHaveAttribute("srcdoc", "<p>House rules snapshot</p>");
    expect(iframe).toHaveAttribute("sandbox", "");
  });

  it("refuses to download or send a document whose bytes have vanished", async () => {
    // `size: null` is the list endpoint's one signal that the stored object
    // could not be read — offering Download and Send on that row only buys
    // the operator a 409.
    server.use(listHandler([doc({ size: null })]));
    setup();

    expect(await screen.findByText(/file unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeDisabled();
  });

  it("keeps a second download from re-enabling the first row mid-flight", async () => {
    globalThis.URL.createObjectURL = vi.fn(() => "blob:mock-url");
    globalThis.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    let releaseFirst = () => {};
    const firstInFlight = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    server.use(
      listHandler([doc({ id: 9 }), doc({ id: 10, filename: "B-AAA-001-contract-10.pdf" })]),
      http.get(`${DOCUMENTS_URL}/9:download`, async () => {
        await firstInFlight;
        return HttpResponse.arrayBuffer(new ArrayBuffer(8));
      }),
      http.get(`${DOCUMENTS_URL}/10:download`, () => HttpResponse.arrayBuffer(new ArrayBuffer(8))),
    );
    setup();

    const [first, second] = await screen.findAllByRole("button", { name: /download/i });
    await userEvent.click(first);
    await userEvent.click(second);

    // The second download must not clear the first one's in-flight state —
    // a shared scalar would re-enable it and allow a duplicate save.
    await waitFor(() => expect(second).toBeEnabled());
    expect(first).toBeDisabled();
    releaseFirst();
    await waitFor(() => expect(first).toBeEnabled());
  });

  it("does not offer a send on a booking with no guest email", async () => {
    // The backend answers `no_recipient` (409) for these — anonymised guests,
    // agency bookings with no guest address. Nothing on this screen can fix
    // it, so the button would only ever fail.
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}`, () =>
        HttpResponse.json({ ...bookingFixture, guest_email: null }),
      ),
      listHandler([doc()]),
    );
    setup();

    expect(await screen.findByText(/no guest email/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /download/i })).toBeEnabled();
  });

  it("disables generate and send for viewers but leaves reading alone", async () => {
    asViewer();
    server.use(listHandler([doc()]));
    setup();

    // Wait on a row button: the header renders before the list resolves.
    expect(await screen.findByRole("button", { name: /download/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /generate contract/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send to guest/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /preview/i })).toBeEnabled();
  });
});
