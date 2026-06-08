import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { EmailTemplateEditorPage } from "../EmailTemplateEditorPage";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("../components/CodeField", async () => await import("@/test/mocks/codeField"));

function makeUser(): UserMe {
  return {
    id: 1,
    email: "u@v.com",
    first_name: "U",
    last_name: "V",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: "en",
  };
}

beforeEach(() => {
  useAuthStore
    .getState()
    .setMe(makeUser(), { role: "admin", is_superuser: false, permissions: [] });
  server.use(
    http.post("/api/v1/email-templates/:key/preview", () =>
      HttpResponse.json({
        rendered_subject: "s",
        rendered_body_html: "<p>b</p>",
        rendered_body_text: "b",
      }),
    ),
  );
});
afterEach(() => {
  useAuthStore.getState().clear();
  server.resetHandlers();
  vi.clearAllMocks();
});

describe("Email template create flow", () => {
  it("publishes a new key then redirects to its detail page", async () => {
    server.use(
      http.put("/api/v1/email-templates/:key", async ({ params }) =>
        HttpResponse.json({
          key: params.key,
          title: "Welcome",
          version: 1,
          is_active: true,
          updated_at: "2026-01-02T10:00:00Z",
          updated_by_id: 1,
          subject_template: "Welcome",
          body_template_mjml: "<mjml></mjml>",
          body_template_html: "",
          notes: "",
        }),
      ),
    );

    renderWithProviders(
      <Routes>
        <Route path="/admin/email-templates/new" element={<EmailTemplateEditorPage />} />
        <Route path="/admin/email-templates/:key" element={<div>detail for key</div>} />
      </Routes>,
      { route: "/admin/email-templates/new" },
    );

    await userEvent.type(screen.getByLabelText("Key"), "welcome.email");
    await userEvent.type(screen.getByLabelText("Title"), "Welcome");
    await userEvent.type(screen.getByLabelText("Subject"), "Welcome");
    await userEvent.type(screen.getByLabelText("MJML body"), "<mjml></mjml>");

    await userEvent.click(screen.getByRole("button", { name: "Create template" }));

    expect(await screen.findByText("detail for key")).toBeInTheDocument();
  });
});
