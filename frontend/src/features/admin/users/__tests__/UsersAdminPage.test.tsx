import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import type { UserMe } from "@/features/auth/schemas";
import { UsersAdminPage } from "../UsersAdminPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const fixture = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      email: "ada@example.com",
      first_name: "Ada",
      last_name: "Lovelace",
      role: "admin",
      is_active: true,
      last_login: null,
      date_joined: "2025-01-02T03:04:05Z",
    },
    {
      id: 2,
      email: "babbage@example.com",
      first_name: "",
      last_name: "",
      role: "reservations",
      is_active: false,
      last_login: null,
      date_joined: "2025-02-01T00:00:00Z",
    },
  ],
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

function asAdmin() {
  useAuthStore.getState().setMe(makeUser(), {
    role: "admin",
    is_superuser: false,
    permissions: [],
  });
}

function asViewer() {
  useAuthStore.getState().setMe(makeUser(), {
    role: "viewer",
    is_superuser: false,
    permissions: [],
  });
}

beforeEach(() => {
  useAuthStore.getState().clear();
});
afterEach(() => {
  server.resetHandlers();
});

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/users" element={<UsersAdminPage />} />
    </Routes>,
    { route: "/admin/users" },
  );
}

describe("UsersAdminPage", () => {
  it("renders rows from /users", async () => {
    asAdmin();
    server.use(http.get("/api/v1/users", () => HttpResponse.json(fixture)));
    setup();
    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("babbage@example.com")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("filters by role", async () => {
    asAdmin();
    const seen: string[] = [];
    server.use(
      http.get("/api/v1/users", ({ request }) => {
        const url = new URL(request.url);
        seen.push(url.searchParams.getAll("role").join(","));
        return HttpResponse.json(fixture);
      }),
    );
    setup();
    await screen.findByText("ada@example.com");
    const triggers = screen.getAllByRole("combobox");
    await userEvent.click(triggers[0]);
    await userEvent.click(await screen.findByRole("option", { name: "Admin" }));
    await waitFor(() => expect(seen).toContain("admin"));
  });

  it("disables new-user button for non-admin", async () => {
    asViewer();
    server.use(http.get("/api/v1/users", () => HttpResponse.json(fixture)));
    setup();
    await screen.findByText("ada@example.com");
    const newBtn = screen.getByRole("button", { name: /new user/i });
    expect(newBtn).toBeDisabled();
  });

  it("opens the create dialog for admins and POSTs to /users", async () => {
    asAdmin();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/users", () => HttpResponse.json(fixture)),
      http.post("/api/v1/users", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 99,
          email: "new@example.com",
          first_name: "",
          last_name: "",
          role: "viewer",
          is_active: true,
        });
      }),
    );
    setup();
    await screen.findByText("ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: /new user/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "new@example.com");
    await userEvent.type(screen.getByLabelText(/^password/i), "supersecret");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    await waitFor(() => expect(postBody).not.toBeNull());
    expect((postBody as Record<string, unknown> | null)?.email).toBe("new@example.com");
  });
});
