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
  currency: "EUR",
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

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => server.resetHandlers());

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
