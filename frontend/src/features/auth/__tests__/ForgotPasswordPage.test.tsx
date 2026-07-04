import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ForgotPasswordPage } from "../ForgotPasswordPage";

function setup(initialPath = "/forgot-password") {
  return renderWithProviders(
    <Routes>
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/login" element={<div>Sign in page</div>} />
    </Routes>,
    { route: initialPath },
  );
}

describe("ForgotPasswordPage", () => {
  it("shows a validation error for an invalid email", async () => {
    setup();
    await userEvent.type(screen.getByLabelText(/email/i), "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
  });

  it("shows the neutral confirmation panel on success", async () => {
    server.use(
      http.post(
        "/api/v1/auth/password-reset:request",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    setup();
    await userEvent.type(screen.getByLabelText(/email/i), "ops@vc.test");
    await userEvent.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(await screen.findByText(/if that email is registered/i)).toBeInTheDocument();
    // The form is replaced — no email field remains.
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
  });

  it("surfaces a throttle (429) error without showing the confirmation", async () => {
    server.use(
      http.post("/api/v1/auth/password-reset:request", () =>
        HttpResponse.json(
          { code: "throttled", detail: "Request was throttled.", field_errors: {} },
          { status: 429 },
        ),
      ),
    );
    setup();
    await userEvent.type(screen.getByLabelText(/email/i), "ops@vc.test");
    await userEvent.click(screen.getByRole("button", { name: /send reset link/i }));
    expect(await screen.findByText(/throttled/i)).toBeInTheDocument();
    expect(screen.queryByText(/if that email is registered/i)).not.toBeInTheDocument();
  });
});
