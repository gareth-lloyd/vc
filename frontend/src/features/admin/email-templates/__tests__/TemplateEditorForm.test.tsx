import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { TemplateEditorForm } from "../components/TemplateEditorForm";
import type { EmailTemplateDetail } from "../schemas";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
// CodeMirror's contenteditable doesn't behave in jsdom — swap CodeField for the
// shared textarea mock so we drive the body/MJML fields like normal inputs.
vi.mock("../components/CodeField", async () => await import("@/test/mocks/codeField"));

const TEMPLATE: EmailTemplateDetail = {
  key: "booking.confirmation",
  title: "Booking Confirmation",
  version: 2,
  is_active: true,
  updated_at: "2026-01-02T10:00:00Z",
  updated_by_id: 1,
  subject_template: "Hi {{ guest_first_name }}",
  body_template_mjml: "<mjml></mjml>",
  body_template_html: "<p>Plain body</p>",
  notes: "",
};

const PREVIEW = {
  rendered_subject: "Hi Ada",
  rendered_body_html: "<p>Hello Ada</p>",
  rendered_body_text: "Hello Ada",
};

function makeUser(overrides: Partial<UserMe> = {}): UserMe {
  return {
    id: 1,
    email: "u@v.com",
    first_name: "U",
    last_name: "V",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: "en",
    ...overrides,
  };
}

function previewHandler() {
  return http.post("/api/v1/email-templates/:key/preview", () => HttpResponse.json(PREVIEW));
}

beforeEach(() => {
  useAuthStore
    .getState()
    .setMe(makeUser(), { role: "admin", is_superuser: false, permissions: [] });
  server.use(previewHandler());
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
  vi.clearAllMocks();
});

describe("TemplateEditorForm (edit)", () => {
  it("publishes a new version and toasts success", async () => {
    server.use(
      http.put("/api/v1/email-templates/:key", () =>
        HttpResponse.json({ ...TEMPLATE, version: 3 }),
      ),
    );
    renderWithProviders(<TemplateEditorForm mode="edit" template={TEMPLATE} />);

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Template published"));
  });

  it("maps a 400 to inline field errors and routes the derived-field error to the alert", async () => {
    server.use(
      http.put("/api/v1/email-templates/:key", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Could not publish.",
            field_errors: {
              subject_template: ["Bad subject tag."],
              body_template_html: ["MJML failed to compile."],
            },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<TemplateEditorForm mode="edit" template={TEMPLATE} />);

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    // Inline error for a real form field.
    expect(await screen.findByText("Bad subject tag.")).toBeInTheDocument();
    // The derived `body_template_html` error has no field, so it's folded into
    // the top-level banner alongside the detail.
    expect(
      await screen.findByText("Could not publish. MJML failed to compile."),
    ).toBeInTheDocument();
    // 4xx keeps the dialog/form in place (no error toast).
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts on a 5xx", async () => {
    server.use(
      http.put("/api/v1/email-templates/:key", () => new HttpResponse(null, { status: 500 })),
    );
    renderWithProviders(<TemplateEditorForm mode="edit" template={TEMPLATE} />);

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("renders the live preview iframe", async () => {
    renderWithProviders(<TemplateEditorForm mode="edit" template={TEMPLATE} />);

    const iframe = (await screen.findByTitle("Rendered email preview")) as HTMLIFrameElement;
    expect(iframe.getAttribute("srcdoc")).toContain("Hello Ada");
  });

  it("disables write affordances for a non-admin", async () => {
    useAuthStore
      .getState()
      .setMe(makeUser(), { role: "viewer", is_superuser: false, permissions: [] });
    renderWithProviders(<TemplateEditorForm mode="edit" template={TEMPLATE} />);

    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Test send" })).toBeDisabled();
  });
});
