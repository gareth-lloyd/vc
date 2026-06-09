import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { BlockRequestDialog } from "../BlockRequestDialog";

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    info: vi.fn(),
  },
}));

function created(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    property: 3,
    date_from: "2026-08-01",
    date_to: "2026-08-08",
    kind: "owner_stay",
    notes: "",
    status: "approved",
    created_at: "2026-06-03T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  toastSuccess.mockClear();
  toastError.mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

describe("BlockRequestDialog", () => {
  it("rejects a non-forward date range with an inline error", async () => {
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/from/i), "2026-08-08");
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-08-01");
    await userEvent.click(screen.getByRole("button", { name: /block dates/i }));

    expect(await screen.findByText(/end date must be after/i)).toBeInTheDocument();
  });

  it("shows an inclusive nights summary as dates are entered", async () => {
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/from/i), "2026-08-01");
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-08-08");

    // [1 Aug, 8 Aug) is 7 nights — the summary must not surface the exclusive 8th.
    expect(await screen.findByTestId("block-nights-summary")).toHaveTextContent(
      "7 nights (1–7 Aug 2026)",
    );
  });

  it("posts the request and toasts on success", async () => {
    let body: unknown = null;
    server.use(
      http.post("/api/v1/owner/block-requests", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created(), { status: 201 });
      }),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={onOpenChange} />);

    await userEvent.type(screen.getByLabelText(/from/i), "2026-08-01");
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-08-08");
    await userEvent.click(screen.getByRole("button", { name: /block dates/i }));

    await waitFor(() => expect(body).toMatchObject({ property: 3, kind: "owner_stay" }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("maps a 409 conflict to a top-level alert and stays open", async () => {
    server.use(
      http.post("/api/v1/owner/block-requests", () =>
        HttpResponse.json(
          { code: "overlapping_booking", detail: "A booking already occupies those dates" },
          { status: 409 },
        ),
      ),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={onOpenChange} />);

    await userEvent.type(screen.getByLabelText(/from/i), "2026-08-01");
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-08-08");
    await userEvent.click(screen.getByRole("button", { name: /block dates/i }));

    expect(await screen.findByText(/overlap an existing booking or block/i)).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("toasts on a 5xx server error", async () => {
    server.use(
      http.post("/api/v1/owner/block-requests", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(<BlockRequestDialog propertyId={3} open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/from/i), "2026-08-01");
    await userEvent.type(screen.getByLabelText(/^to$/i), "2026-08-08");
    await userEvent.click(screen.getByRole("button", { name: /block dates/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});
