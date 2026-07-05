import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { ResetPasswordPage } from "../ResetPasswordPage";

function setup(initialPath: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/login" element={<div>Sign in page</div>} />
      <Route path="/forgot-password" element={<div>Forgot page</div>} />
    </Routes>,
    { route: initialPath },
  );
}

describe("ResetPasswordPage", () => {
  it("shows the invalid-link state when there is no token", () => {
    setup("/reset-password");
    expect(screen.getByText(/this link is invalid or has expired/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
  });

  it("validates that the two passwords match", async () => {
    setup("/reset-password?token=abc");
    await userEvent.type(screen.getByLabelText(/^new password/i), "longenough");
    await userEvent.type(screen.getByLabelText(/confirm/i), "different1");
    await userEvent.click(screen.getByRole("button", { name: /reset password/i }));
    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it("navigates to /login on a successful reset", async () => {
    server.use(
      http.post(
        "/api/v1/auth/password-reset:confirm",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    setup("/reset-password?token=abc");
    await userEvent.type(screen.getByLabelText(/^new password/i), "longenough");
    await userEvent.type(screen.getByLabelText(/confirm/i), "longenough");
    await userEvent.click(screen.getByRole("button", { name: /reset password/i }));
    await waitFor(() => expect(screen.getByText("Sign in page")).toBeInTheDocument());
  });

  it("shows the invalid-link state when the server rejects an expired token", async () => {
    server.use(
      http.post("/api/v1/auth/password-reset:confirm", () =>
        HttpResponse.json(
          {
            code: "password_reset_token_expired",
            detail: "This reset link has expired.",
            field_errors: {},
          },
          { status: 400 },
        ),
      ),
    );
    setup("/reset-password?token=stale");
    await userEvent.type(screen.getByLabelText(/^new password/i), "longenough");
    await userEvent.type(screen.getByLabelText(/confirm/i), "longenough");
    await userEvent.click(screen.getByRole("button", { name: /reset password/i }));
    expect(await screen.findByText(/this link is invalid or has expired/i)).toBeInTheDocument();
    expect(screen.getByText(/request a new link/i)).toBeInTheDocument();
  });
});
