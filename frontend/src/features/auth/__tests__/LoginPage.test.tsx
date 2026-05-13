import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "../store";
import { LoginPage } from "../LoginPage";

const fixtureUser = {
  id: 1,
  email: "ops@vc.test",
  first_name: "Ops",
  last_name: "User",
  phone: null,
  role: "operator",
  is_active: true,
  is_staff: true,
  is_superuser: false,
  tfa_method: null,
  tfa_enrolled_at: null,
  last_login: null,
};

beforeEach(() => {
  useAuthStore.getState().clear();
});

afterEach(() => {
  useAuthStore.getState().clear();
});

function setup(initialPath = "/login") {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/login/2fa" element={<div>2FA page</div>} />
      <Route path="/dashboard" element={<div>Dashboard</div>} />
    </Routes>,
    { route: initialPath },
  );
}

describe("LoginPage", () => {
  it("shows validation errors when fields are empty", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
  });

  it("navigates to /dashboard on successful login (no 2FA)", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ tfa_required: false, user: fixtureUser }),
      ),
    );
    setup();
    await userEvent.type(screen.getByLabelText(/email/i), "ops@vc.test");
    await userEvent.type(screen.getByLabelText(/password/i), "secret");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
  });

  it("navigates to /login/2fa and stores pendingTfa when 2FA is required", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ tfa_required: true, challenge_token: "tok", expires_in_seconds: 300 }),
      ),
    );
    setup();
    await userEvent.type(screen.getByLabelText(/email/i), "ops@vc.test");
    await userEvent.type(screen.getByLabelText(/password/i), "secret");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByText("2FA page")).toBeInTheDocument());
    expect(useAuthStore.getState().pendingTfa?.challengeToken).toBe("tok");
  });

  it("renders the server error message on 401", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          { code: "invalid_credentials", detail: "Invalid email or password.", field_errors: {} },
          { status: 401 },
        ),
      ),
    );
    setup();
    await userEvent.type(screen.getByLabelText(/email/i), "ops@vc.test");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });

  it("respects state.next when present", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ tfa_required: false, user: fixtureUser }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/properties" element={<div>Properties</div>} />
      </Routes>,
      {
        routerProps: { initialEntries: [{ pathname: "/login", state: { next: "/properties" } }] },
      },
    );
    await userEvent.type(screen.getByLabelText(/email/i), "a@b.com");
    await userEvent.type(screen.getByLabelText(/password/i), "secret");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(screen.getByText("Properties")).toBeInTheDocument());
  });
});
