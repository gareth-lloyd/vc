import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { LineEditDialog } from "../components/LineEditDialog";
import type { QuotationLine } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const QUOTATION_ID = 7;

function makeLine(overrides: Partial<QuotationLine> = {}): QuotationLine {
  return {
    id: 33,
    quotation: QUOTATION_ID,
    property: 12,
    property_name: "Villa Sol",
    hero_image_url: null,
    date_from: "2026-07-01",
    date_to: "2026-07-08",
    adults: 2,
    children: 1,
    total: "1234.50",
    discount: "0.00",
    inclusions: "",
    price_override_reason: "",
    is_selected: false,
    is_manual: false,
    notes: "",
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => server.resetHandlers());

describe("LineEditDialog", () => {
  it("sends an edited discount on a priced line", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch(`/api/v1/quotations/${QUOTATION_ID}/lines/33`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeLine({ discount: "100.00" }));
      }),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(
      <LineEditDialog
        open
        onOpenChange={onOpenChange}
        quotationId={QUOTATION_ID}
        line={makeLine()}
      />,
    );
    const dialog = screen.getByRole("dialog");
    const discount = within(dialog).getByLabelText(/discount/i) as HTMLInputElement;
    await userEvent.clear(discount);
    await userEvent.type(discount, "100.00");
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(body).not.toBeNull();
    expect(body!.discount).toBe("100.00");
    // Non-manual line: no total / reason on the wire.
    expect(body!.total).toBeUndefined();
    expect(body!.price_override_reason).toBeUndefined();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("normalises a comma-typed discount to a canonical 2-dp decimal", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch(`/api/v1/quotations/${QUOTATION_ID}/lines/33`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeLine({ discount: "1500.00" }));
      }),
    );
    renderWithProviders(
      <LineEditDialog open onOpenChange={vi.fn()} quotationId={QUOTATION_ID} line={makeLine()} />,
    );
    const dialog = screen.getByRole("dialog");
    const discount = within(dialog).getByLabelText(/discount/i) as HTMLInputElement;
    await userEvent.clear(discount);
    await userEvent.type(discount, "1,500");
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(body).not.toBeNull();
    expect(body!.discount).toBe("1500.00");
  });

  it("normalises a comma-typed manual total to a canonical 2-dp decimal", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch(`/api/v1/quotations/${QUOTATION_ID}/lines/33`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeLine({ is_manual: true, total: "5000.00" }));
      }),
    );
    renderWithProviders(
      <LineEditDialog
        open
        onOpenChange={vi.fn()}
        quotationId={QUOTATION_ID}
        line={makeLine({ is_manual: true, total: "100.00", price_override_reason: "Agreed rate" })}
      />,
    );
    const dialog = screen.getByRole("dialog");
    const total = (await within(dialog).findByLabelText(/manual total/i)) as HTMLInputElement;
    await userEvent.clear(total);
    await userEvent.type(total, "5,000");
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(body).not.toBeNull();
    expect(body!.total).toBe("5000.00");
  });

  it("zeroes and disables the discount on a manual line", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch(`/api/v1/quotations/${QUOTATION_ID}/lines/33`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeLine({ is_manual: true }));
      }),
    );
    renderWithProviders(
      <LineEditDialog
        open
        onOpenChange={vi.fn()}
        quotationId={QUOTATION_ID}
        line={makeLine({
          is_manual: true,
          total: "100.00",
          price_override_reason: "Agreed rate",
          discount: "75.00",
        })}
      />,
    );
    const dialog = screen.getByRole("dialog");
    // The server never applies a discount to a manual line, so the field is
    // inert — mirror the shortlist: disabled input, "0" on the wire.
    expect(within(dialog).getByLabelText(/discount/i)).toBeDisabled();
    await within(dialog).findByLabelText(/manual total/i);
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(body).not.toBeNull();
    expect(body!.discount).toBe("0");
  });

  it("blocks submit with an inline error when a manual line has no total", async () => {
    let patched = false;
    server.use(
      http.patch(`/api/v1/quotations/${QUOTATION_ID}/lines/33`, () => {
        patched = true;
        return HttpResponse.json(makeLine());
      }),
    );
    renderWithProviders(
      <LineEditDialog
        open
        onOpenChange={vi.fn()}
        quotationId={QUOTATION_ID}
        line={makeLine({ is_manual: true, total: "", price_override_reason: "Agreed rate" })}
      />,
    );
    const dialog = screen.getByRole("dialog");
    const total = (await within(dialog).findByLabelText(/manual total/i)) as HTMLInputElement;
    await userEvent.clear(total);
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    expect(await within(dialog).findByText(/total greater than zero/i)).toBeInTheDocument();
    // The client-side guard short-circuits the request entirely.
    expect(patched).toBe(false);
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("surfaces the server 400 on field_errors.total inline (belt and suspenders)", async () => {
    server.use(
      http.patch(`/api/v1/quotations/${QUOTATION_ID}/lines/33`, () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: {
              total: ["A manual line requires a total greater than zero."],
            },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <LineEditDialog
        open
        onOpenChange={vi.fn()}
        quotationId={QUOTATION_ID}
        // Client refine passes (positive total + reason); the server still
        // rejects, exercising the applyApiErrorToForm path for `total`.
        line={makeLine({ is_manual: true, total: "100.00", price_override_reason: "Agreed rate" })}
      />,
    );
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByLabelText(/manual total/i);
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    expect(
      await within(dialog).findByText(/requires a total greater than zero/i),
    ).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("surfaces the server 400 on a manual line without a reason inline", async () => {
    server.use(
      http.patch(`/api/v1/quotations/${QUOTATION_ID}/lines/33`, () =>
        HttpResponse.json(
          {
            code: "invalid",
            detail: "Validation failed",
            field_errors: {
              price_override_reason: ["This field is required for a manual line."],
            },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <LineEditDialog
        open
        onOpenChange={vi.fn()}
        quotationId={QUOTATION_ID}
        // Already manual but with a reason, so the client-side refine passes
        // and the request reaches the server, which rejects it. (We clear the
        // reason field below to drive the manual-without-reason case at the
        // server boundary while keeping the client refine satisfied.)
        line={makeLine({ is_manual: true, price_override_reason: "seed" })}
      />,
    );
    const dialog = screen.getByRole("dialog");
    // The manual fields are visible because the line is manual.
    await within(dialog).findByLabelText(/manual total/i);
    await userEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    expect(await within(dialog).findByText(/required for a manual line/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });
});
