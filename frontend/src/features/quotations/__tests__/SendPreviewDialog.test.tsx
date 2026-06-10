import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { SendPreviewDialog } from "../components/SendPreviewDialog";
import type { QuotationDetail } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const QUOTATION: QuotationDetail = {
  id: 7,
  reference: "Q-2026-007",
  status: "draft",
  enquiry: 11,
  guest: 42,
  agent: null,
  is_unbranded: false,
  expires_at: "2026-06-01T00:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  cancel_reason: "",
  lines: [],
};

const PREVIEW = {
  html: "<html><body><h1>Your villa quote</h1></body></html>",
  subject: "Your villa quote",
  intro: "Dear guest",
  signoff: "Kind regards",
};

function previewHandler() {
  return http.get("/api/v1/quotations/7:preview", () => HttpResponse.json(PREVIEW));
}

// Installs a clipboard spy that captures the actual string content per MIME
// flavour. jsdom Blobs don't expose their content via .text(), so we spy on
// the Blob constructor to record the parts as they're built.
function installClipboardSpy() {
  const write = vi.fn().mockResolvedValue(undefined);
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
  return { write, flavours };
}

const originalClipboard = navigator.clipboard;
const originalClipboardItem = (globalThis as { ClipboardItem?: unknown }).ClipboardItem;

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
  Object.defineProperty(navigator, "clipboard", {
    value: originalClipboard,
    configurable: true,
  });
  (globalThis as { ClipboardItem?: unknown }).ClipboardItem = originalClipboardItem;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SendPreviewDialog", () => {
  it("renders the preview iframe and seeds the editable fields", async () => {
    server.use(previewHandler());
    renderWithProviders(<SendPreviewDialog open onOpenChange={vi.fn()} quotation={QUOTATION} />);
    const dialog = screen.getByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByTitle(/guest quote preview/i)).toBeInTheDocument(),
    );
    const iframe = within(dialog).getByTitle(/guest quote preview/i) as HTMLIFrameElement;
    expect(iframe.getAttribute("srcdoc")).toContain("Your villa quote");
    expect(iframe.getAttribute("sandbox")).toBe("");
    const subject = within(dialog).getByLabelText(/subject/i) as HTMLInputElement;
    expect(subject.value).toBe("Your villa quote");
  });

  it("submits the edited overrides to :send and toasts success", async () => {
    let body: unknown = null;
    server.use(
      previewHandler(),
      http.post("/api/v1/quotations/7:send", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...QUOTATION, status: "sent" });
      }),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(
      <SendPreviewDialog open onOpenChange={onOpenChange} quotation={QUOTATION} />,
    );
    const dialog = screen.getByRole("dialog");
    const subject = await within(dialog).findByLabelText(/subject/i);
    await userEvent.clear(subject);
    await userEvent.type(subject, "Custom subject");
    await userEvent.click(within(dialog).getByRole("button", { name: /^send to guest$/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(body).toEqual({
      subject: "Custom subject",
      intro: "Dear guest",
      signoff: "Kind regards",
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("surfaces a 400 field error inline and does NOT toast", async () => {
    server.use(
      previewHandler(),
      http.post("/api/v1/quotations/7:send", () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: { subject: ["This subject is too long"] },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<SendPreviewDialog open onOpenChange={vi.fn()} quotation={QUOTATION} />);
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByLabelText(/subject/i);
    await userEvent.click(within(dialog).getByRole("button", { name: /^send to guest$/i }));

    expect(await within(dialog).findByText(/too long/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("re-fetches the preview with override query params as the operator edits", async () => {
    const seen: Array<Record<string, string | null>> = [];
    server.use(
      http.get("/api/v1/quotations/7:preview", ({ request }) => {
        const url = new URL(request.url);
        seen.push({
          subject: url.searchParams.get("subject"),
          intro: url.searchParams.get("intro"),
          signoff: url.searchParams.get("signoff"),
        });
        const subject = url.searchParams.get("subject");
        return HttpResponse.json({
          ...PREVIEW,
          // Echo the edited subject into the html so we can assert the iframe
          // reflects the edit.
          html: `<html><body>${subject ?? PREVIEW.subject}</body></html>`,
          subject: subject ?? PREVIEW.subject,
        });
      }),
    );
    renderWithProviders(<SendPreviewDialog open onOpenChange={vi.fn()} quotation={QUOTATION} />);
    const dialog = screen.getByRole("dialog");
    const subject = await within(dialog).findByLabelText(/subject/i);
    // First fetch has no overrides (seed from defaults).
    await waitFor(() => expect(seen.length).toBeGreaterThanOrEqual(1));
    expect(seen[0].subject).toBeNull();

    await userEvent.clear(subject);
    await userEvent.type(subject, "Edited subject");

    // The debounced override fetch fires and the iframe srcDoc reflects the edit.
    await waitFor(() => {
      const iframe = within(dialog).getByTitle(/guest quote preview/i) as HTMLIFrameElement;
      expect(iframe.getAttribute("srcdoc")).toContain("Edited subject");
    });
    expect(seen.some((q) => q.subject === "Edited subject")).toBe(true);
  });

  it("copies the loaded html + a plain-text flavour, then marks manually sent", async () => {
    let manuallySent = false;
    server.use(
      previewHandler(),
      http.post("/api/v1/quotations/7:mark-manually-sent", () => {
        manuallySent = true;
        return HttpResponse.json({ ...QUOTATION, status: "sent" });
      }),
    );

    const { write, flavours } = installClipboardSpy();
    const onOpenChange = vi.fn();
    renderWithProviders(
      <SendPreviewDialog open onOpenChange={onOpenChange} quotation={QUOTATION} />,
    );
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByLabelText(/subject/i);
    await userEvent.click(within(dialog).getByRole("button", { name: /copy quote to clipboard/i }));

    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    expect(Object.keys(flavours)).toEqual(["text/html", "text/plain"]);
    // The rich flavour keeps the markup; the plain flavour is readable text.
    expect(flavours["text/html"]).toContain("Your villa quote");
    expect(flavours["text/plain"]).toContain("Your villa quote");
    expect(flavours["text/plain"]).not.toContain("<html");
    expect(flavours["text/plain"]).not.toContain("<body");
    await waitFor(() => expect(manuallySent).toBe(true));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("toasts on a 5xx send failure", async () => {
    server.use(
      previewHandler(),
      http.post("/api/v1/quotations/7:send", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(<SendPreviewDialog open onOpenChange={vi.fn()} quotation={QUOTATION} />);
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByLabelText(/subject/i);
    await userEvent.click(within(dialog).getByRole("button", { name: /^send to guest$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
  });
});
