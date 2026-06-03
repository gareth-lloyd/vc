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
    status: "pending",
    review_note: "",
    reviewed_at: null,
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
    await userEvent.click(screen.getByRole("button", { name: /submit request/i }));

    expect(await screen.findByText(/end date must be after/i)).toBeInTheDocument();
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
    await userEvent.click(screen.getByRole("button", { name: /submit request/i }));

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
    await userEvent.click(screen.getByRole("button", { name: /submit request/i }));

    expect(await screen.findByText(/a booking already occupies/i)).toBeInTheDocument();
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
    await userEvent.click(screen.getByRole("button", { name: /submit request/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});
