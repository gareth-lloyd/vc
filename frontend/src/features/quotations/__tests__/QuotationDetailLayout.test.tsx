import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { QuotationDetailLayout } from "../QuotationDetailLayout";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
import { toast } from "sonner";

const baseQuotation = {
  id: 7,
  reference: "Q-2026-007",
  status: "draft",
  enquiry: 11,
  guest: 42,
  agent: null,
  expires_at: "2026-06-01T00:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  cancel_reason: "",
  lines: [],
};

const baseLine = {
  id: 33,
  quotation: 7,
  property: 12,
  date_from: "2026-07-04",
  date_to: "2026-07-11",
  adults: 2,
  children: 1,
  currency: "EUR",
  total: "1234.50",
  is_selected: true,
  is_manual: false,
  notes: "",
};

function quotationHandlers(
  quotation: Record<string, unknown>,
  lines: Array<Record<string, unknown>>,
) {
  return [
    http.get("/api/v1/quotations/7", () => HttpResponse.json(quotation)),
    http.get("/api/v1/quotations/7/lines", () =>
      HttpResponse.json({ count: lines.length, next: null, previous: null, results: lines }),
    ),
  ];
}

const noLinesHandlers = quotationHandlers(baseQuotation, []);

afterEach(() => {
  server.resetHandlers();
  useAuthStore.getState().clear();
});

function asReservationsUser() {
  // Only `role` and `isSuperuser` matter for `useHasReservationsRole` —
  // leave `user` null to avoid pinning the full UserMe shape in this test.
  useAuthStore.setState({
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/enquiries/quotes/:id" element={<QuotationDetailLayout />} />
    </Routes>,
    { route: "/enquiries/quotes/7" },
  );
}

describe("QuotationDetailLayout", () => {
  beforeEach(() => server.use(...noLinesHandlers));

  it("renders the reference and status badge", async () => {
    setup();
    await waitFor(() => expect(screen.getAllByText("Q-2026-007").length).toBeGreaterThan(0));
  });

  it("renders the empty lines state when there are no lines", async () => {
    setup();
    expect(await screen.findByText(/no lines yet/i)).toBeInTheDocument();
  });

  it("breadcrumb links back to the Quotes tab under Enquiries", async () => {
    setup();
    await waitFor(() => expect(screen.getAllByText("Q-2026-007").length).toBeGreaterThan(0));
    expect(screen.getByRole("link", { name: "Quotes" })).toHaveAttribute(
      "href",
      "/enquiries/quotes",
    );
  });

  it("renders line rows when the lines endpoint returns data", async () => {
    server.resetHandlers();
    server.use(
      ...quotationHandlers(baseQuotation, [{ ...baseLine, changeover_shifted_from: "2026-07-01" }]),
    );
    setup();
    expect(await screen.findByText("#33")).toBeInTheDocument();
    expect(screen.getByText("#12")).toBeInTheDocument();
    expect(screen.getByText(/€1,234\.50 EUR/)).toBeInTheDocument();
    // The arrival was shifted to the changeover day — the detail line table
    // surfaces the same "we moved your dates" note as the builder/convert.
    expect(
      screen.getByText(/arrival moved from .+ to the property's changeover day/i),
    ).toBeInTheDocument();
    // is_selected renders as a badge, not a Yes/No column.
    expect(screen.getByText("Selected")).toBeInTheDocument();
  });

  it("shows a discount only when it is non-zero", async () => {
    server.resetHandlers();
    server.use(
      ...quotationHandlers(baseQuotation, [
        { ...baseLine, discount: "0.00" },
        { ...baseLine, id: 34, property: 13, discount: "150.00" },
      ]),
    );
    setup();
    const discountedCard = (await screen.findByText("#34")).closest("li")!;
    expect(within(discountedCard).getByText(/discount/i)).toBeInTheDocument();
    expect(within(discountedCard).getByText(/€150\.00 EUR/)).toBeInTheDocument();
    const zeroCard = screen.getByText("#33").closest("li")!;
    expect(within(zeroCard).queryByText(/discount/i)).not.toBeInTheDocument();
  });

  it("renders mixed-currency lines each in their own currency", async () => {
    // Currency lives per line (GAP-014) — a saved quote can mix €/£ lines.
    server.resetHandlers();
    server.use(
      ...quotationHandlers(baseQuotation, [
        baseLine,
        { ...baseLine, id: 34, property: 13, currency: "GBP", total: "980.00" },
      ]),
    );
    setup();
    expect(await screen.findByText(/€1,234\.50 EUR/)).toBeInTheDocument();
    expect(screen.getByText(/£980\.00 GBP/)).toBeInTheDocument();
  });

  it("links the line's property name to the property detail page", async () => {
    server.resetHandlers();
    server.use(
      ...quotationHandlers(baseQuotation, [{ ...baseLine, property_name: "Villa Aurora" }]),
    );
    setup();
    expect(await screen.findByRole("link", { name: "Villa Aurora" })).toHaveAttribute(
      "href",
      "/properties/12/details",
    );
  });

  it("disables action buttons when the user lacks the reservations role", async () => {
    setup();
    const sendBtn = await screen.findByRole("button", { name: /send to guest/i });
    expect(sendBtn).toBeDisabled();
    expect(screen.getByRole("button", { name: /^duplicate$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /withdraw/i })).toBeDisabled();
    // Converting moved to the per-row Book action — no rail button anymore.
    expect(screen.queryByRole("button", { name: /convert to booking/i })).not.toBeInTheDocument();
  });

  it("enables send/duplicate/withdraw with the reservations role", async () => {
    asReservationsUser();
    setup();
    expect(await screen.findByRole("button", { name: /send to guest/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^duplicate$/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /withdraw/i })).toBeEnabled();
  });

  it("row Book is disabled on a draft quote and enabled once sent", async () => {
    asReservationsUser();
    server.resetHandlers();
    server.use(...quotationHandlers(baseQuotation, [baseLine]));
    const view = setup();
    expect(await screen.findByRole("button", { name: /^book$/i })).toBeDisabled();

    view.unmount();
    server.resetHandlers();
    server.use(...quotationHandlers({ ...baseQuotation, status: "sent" }, [baseLine]));
    setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /^book$/i })).toBeEnabled());
  });

  it("row Book opens the convert dialog preselected to that line", async () => {
    asReservationsUser();
    server.resetHandlers();
    server.use(
      ...quotationHandlers({ ...baseQuotation, status: "sent" }, [
        { ...baseLine, is_selected: false },
        { ...baseLine, id: 34, property: 13, is_selected: false },
      ]),
    );
    setup();
    const bookButtons = await screen.findAllByRole("button", { name: /^book$/i });
    await userEvent.click(bookButtons[1]);
    const dialog = await screen.findByRole("dialog");
    // The second row's line (id 34) is the preselected radio — not line 33,
    // which the default "first line" pick would have chosen.
    await waitFor(() => expect(within(dialog).getByDisplayValue("34")).toBeChecked());
    expect(within(dialog).getByDisplayValue("33")).not.toBeChecked();
  });

  it("places a hold from the row action after confirmation", async () => {
    asReservationsUser();
    server.resetHandlers();
    let holdCalled = false;
    server.use(
      ...quotationHandlers(baseQuotation, [baseLine]),
      http.post("/api/v1/quotations/7/lines/33:hold", () => {
        holdCalled = true;
        return HttpResponse.json({
          ...baseLine,
          hold: {
            id: 5,
            date_from: "2026-07-04",
            date_to: "2026-07-11",
            expires_at: "2026-07-06T12:00:00Z",
          },
        });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /^hold$/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /place hold/i }));
    await waitFor(() => expect(holdCalled).toBe(true));
  });

  it("shows the held badge and releases via the row action", async () => {
    asReservationsUser();
    server.resetHandlers();
    let releaseCalled = false;
    const heldLine = {
      ...baseLine,
      hold: {
        id: 5,
        date_from: "2026-07-04",
        date_to: "2026-07-11",
        expires_at: "2026-07-06T12:00:00Z",
      },
    };
    server.use(
      ...quotationHandlers(baseQuotation, [heldLine]),
      http.post("/api/v1/quotations/7/lines/33:release-hold", () => {
        releaseCalled = true;
        return HttpResponse.json({ ...baseLine, hold: null });
      }),
    );
    setup();
    expect(await screen.findByText(/held until/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^hold$/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /release hold/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /^release$/i }));
    await waitFor(() => expect(releaseCalled).toBe(true));
  });

  it("surfaces the backend conflict detail when a hold 409s", async () => {
    asReservationsUser();
    server.resetHandlers();
    server.use(
      ...quotationHandlers(baseQuotation, [baseLine]),
      http.post("/api/v1/quotations/7/lines/33:hold", () =>
        HttpResponse.json(
          {
            code: "hold_unavailable",
            detail: "Villa Sol is unavailable for 2026-07-04..2026-07-11 — already held.",
            field_errors: {},
          },
          { status: 409 },
        ),
      ),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /^hold$/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /place hold/i }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/already held/i)),
    );
  });

  it("posts to :send on confirm after the preview loads", async () => {
    asReservationsUser();
    let sendCalled = false;
    server.use(
      http.get("/api/v1/quotations/7:preview", () =>
        HttpResponse.json({
          html: "<html><body>Hello</body></html>",
          subject: "Your quote",
          intro: "Dear guest",
          signoff: "Kind regards",
        }),
      ),
      http.post("/api/v1/quotations/7:send", () => {
        sendCalled = true;
        return HttpResponse.json({ ...baseQuotation, status: "sent" });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /send to guest/i }));
    const dialog = await screen.findByRole("dialog");
    // The submit button is enabled only once the preview resolves.
    const sendBtn = await within(dialog).findByRole("button", { name: /^send to guest$/i });
    await userEvent.click(sendBtn);
    await waitFor(() => expect(sendCalled).toBe(true));
  });

  it("posts to :withdraw with the captured reason", async () => {
    asReservationsUser();
    let captured: { reason?: string } = {};
    server.use(
      http.post("/api/v1/quotations/7:withdraw", async ({ request }) => {
        captured = (await request.json()) as { reason: string };
        return HttpResponse.json({ ...baseQuotation, status: "cancelled" });
      }),
    );
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /withdraw/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(
      within(dialog).getByLabelText(/reason/i),
      "Quote superseded by a new option.",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: /^withdraw$/i }));
    await waitFor(() => expect(captured.reason).toBe("Quote superseded by a new option."));
  });

  it("copy-to-clipboard waits for the prefetched preview, then writes synchronously", async () => {
    asReservationsUser();
    let manuallySent = false;
    server.use(
      http.get("/api/v1/quotations/7:preview", () =>
        HttpResponse.json({
          html: "<html><body><h1>Villa Sol quote</h1></body></html>",
          subject: "Your quote",
          intro: "Dear guest",
          signoff: "Kind regards",
        }),
      ),
      http.post("/api/v1/quotations/7:mark-manually-sent", () => {
        manuallySent = true;
        return HttpResponse.json({ ...baseQuotation, status: "sent" });
      }),
    );

    const originalClipboard = navigator.clipboard;
    const originalClipboardItem = (globalThis as { ClipboardItem?: unknown }).ClipboardItem;
    const write = vi.fn().mockResolvedValue(undefined);
    // jsdom Blobs hide their content, so spy on the Blob constructor to record
    // each flavour's string as it's built.
    const blobContent = new WeakMap<object, string>();
    const RealBlob = globalThis.Blob;
    class SpyBlob extends RealBlob {
      constructor(parts: BlobPart[], opts?: BlobPropertyBag) {
        super(parts, opts);
        blobContent.set(this, parts.map(String).join(""));
      }
    }
    vi.stubGlobal("Blob", SpyBlob);
    const flavours: Record<string, string> = {};
    class FakeClipboardItem {
      constructor(items: Record<string, Blob>) {
        for (const [mime, blob] of Object.entries(items)) {
          flavours[mime] = blobContent.get(blob) ?? "";
        }
      }
    }
    Object.defineProperty(navigator, "clipboard", {
      value: { write, writeText: vi.fn() },
      configurable: true,
    });
    (globalThis as { ClipboardItem?: unknown }).ClipboardItem = FakeClipboardItem;

    try {
      setup();
      // Before the prefetch resolves the rail copy button is disabled (it
      // never await-then-writes). Once the cached preview lands it enables.
      // ActionButton swaps the tooltip-wrapped (disabled) node for a plain
      // button when the reason clears, so re-query rather than holding a node.
      await waitFor(() =>
        expect(screen.getByRole("button", { name: /copy quote to clipboard/i })).toBeEnabled(),
      );
      await userEvent.click(screen.getByRole("button", { name: /copy quote to clipboard/i }));

      await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
      expect(Object.keys(flavours)).toEqual(["text/html", "text/plain"]);
      expect(flavours["text/plain"]).toContain("Villa Sol quote");
      expect(flavours["text/plain"]).not.toContain("<html");
      await waitFor(() => expect(manuallySent).toBe(true));
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: originalClipboard,
        configurable: true,
      });
      (globalThis as { ClipboardItem?: unknown }).ClipboardItem = originalClipboardItem;
      vi.unstubAllGlobals();
      vi.restoreAllMocks();
    }
  });

  it("renders the not-found error on 404", async () => {
    server.resetHandlers();
    server.use(http.get("/api/v1/quotations/7", () => HttpResponse.json({}, { status: 404 })));
    setup();
    expect(await screen.findByText(/quotation not found/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
