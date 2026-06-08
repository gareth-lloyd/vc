import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { TestSendDialog } from "../components/TestSendDialog";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});

describe("TestSendDialog", () => {
  it("dispatches a test send and toasts the log id", async () => {
    server.use(
      http.post("/api/v1/email-templates/:key/test-send", () =>
        HttpResponse.json({ id: 42, status: "QUEUED" }, { status: 201 }),
      ),
    );
    renderWithProviders(
      <TestSendDialog templateKey="booking.confirmation" open onOpenChange={() => {}} />,
    );

    await userEvent.type(screen.getByLabelText("Recipient"), "qa@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send test" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Test email queued (log #42)"));
  });

  it("surfaces a 4xx in the alert without a toast", async () => {
    server.use(
      http.post("/api/v1/email-templates/:key/test-send", () =>
        HttpResponse.json(
          { code: "validation_error", detail: "No recipient on file.", field_errors: {} },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <TestSendDialog templateKey="booking.confirmation" open onOpenChange={() => {}} />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Send test" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No recipient on file.");
    expect(toast.error).not.toHaveBeenCalled();
  });
});
