import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ContestDialog } from "../ContestDialog";

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    info: vi.fn(),
  },
}));

beforeEach(() => {
  toastSuccess.mockClear();
  toastError.mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

describe("ContestDialog", () => {
  it("posts the reason and toasts on success", async () => {
    let body: unknown = null;
    server.use(
      http.post("/api/v1/owner-block-updates/7:contest", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          id: 7,
          kind: "created",
          actor: 9,
          created_at: "2026-06-03T10:00:00Z",
          block: {
            id: 50,
            property: 3,
            property_name: "Villa Anemoi",
            date_from: "2026-08-01",
            date_to: "2026-08-08",
            kind: "owner_stay",
            notes: "",
            status: "approved",
            created_by: 9,
          },
          contested: { at: "2026-06-04T08:00:00Z", by: 12, reason: "Double booked" },
          is_seen: true,
        });
      }),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(<ContestDialog updateId={7} open onOpenChange={onOpenChange} />);

    await userEvent.type(screen.getByLabelText(/reason/i), "Double booked");
    await userEvent.click(screen.getByRole("button", { name: /contest block/i }));

    await waitFor(() => expect(body).toMatchObject({ reason: "Double booked" }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("maps a 400 to an inline field error and stays open", async () => {
    server.use(
      http.post("/api/v1/owner-block-updates/7:contest", () =>
        HttpResponse.json(
          { detail: "Invalid", field_errors: { reason: ["This field may not be blank."] } },
          { status: 400 },
        ),
      ),
    );
    const onOpenChange = vi.fn();
    renderWithProviders(<ContestDialog updateId={7} open onOpenChange={onOpenChange} />);

    await userEvent.type(screen.getByLabelText(/reason/i), "x");
    await userEvent.click(screen.getByRole("button", { name: /contest block/i }));

    expect(await screen.findByText(/may not be blank/i)).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("toasts on a 5xx server error", async () => {
    server.use(
      http.post("/api/v1/owner-block-updates/7:contest", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderWithProviders(<ContestDialog updateId={7} open onOpenChange={() => {}} />);

    await userEvent.type(screen.getByLabelText(/reason/i), "x");
    await userEvent.click(screen.getByRole("button", { name: /contest block/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});
