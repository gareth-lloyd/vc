import { http, HttpResponse } from "msw";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { CompanyDetailLayout } from "../CompanyDetailLayout";
import { DetailsTab } from "../tabs/DetailsTab";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
import { toast } from "sonner";

const companyFixture = {
  id: 7,
  name: "Analytical Engines",
  org_type: "agency",
  status: "active",
  email: "ops@analytical.test",
  phone: "+44 7000 000 000",
  address_line_1: "1 Babbage Way",
  address_line_2: null,
  town: "London",
  post_code: "EC1A 1AA",
  website_url: "https://example.com",
  notes: "Long-standing partner agency.",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

function setup(initial: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/companies/:id" element={<CompanyDetailLayout />}>
        <Route index element={<Navigate to="details" replace />} />
        <Route path="details" element={<DetailsTab />} />
      </Route>
      <Route path="/companies" element={<div>Companies list</div>} />
    </Routes>,
    { route: initial },
  );
}

beforeEach(() => {
  // The header edit/delete actions gate on the Reservations role.
  useAuthStore.setState({ isSuperuser: true, status: "authenticated" });
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  useAuthStore.setState({ isSuperuser: false, role: null, status: "idle" });
  server.resetHandlers();
});

describe("CompanyDetailLayout", () => {
  it("renders the company name and details tab", async () => {
    server.use(http.get("/api/v1/organisations/7", () => HttpResponse.json(companyFixture)));
    setup("/companies/7/details");
    await waitFor(() => expect(screen.getAllByText("Analytical Engines")[0]).toBeInTheDocument());
    expect(await screen.findByText("ops@analytical.test")).toBeInTheDocument();
    expect(screen.getByText("+44 7000 000 000")).toBeInTheDocument();
  });

  it("shows a PROTECT toast when delete returns 409 {code:'protected'}", async () => {
    server.use(
      http.get("/api/v1/organisations/7", () => HttpResponse.json(companyFixture)),
      http.delete("/api/v1/organisations/7", () =>
        HttpResponse.json({ code: "protected", detail: "Protected" }, { status: 409 }),
      ),
    );
    setup("/companies/7/details");
    await screen.findByText("ops@analytical.test");

    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    // ConfirmDialog confirm button (also labelled Delete).
    const confirmButtons = await screen.findAllByRole("button", { name: /delete/i });
    await userEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "This company can't be deleted while it still has linked agents.",
      ),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("CompanyDetailLayout error differentiation", () => {
  it("shows 'Company not found' on 404 without a retry button", async () => {
    server.use(
      http.get("/api/v1/organisations/999", () =>
        HttpResponse.json({ detail: "Not found." }, { status: 404 }),
      ),
    );
    renderWithProviders(
      <Routes>
        <Route path="/companies/:id" element={<CompanyDetailLayout />}>
          <Route index element={<Navigate to="details" replace />} />
          <Route path="details" element={<DetailsTab />} />
        </Route>
      </Routes>,
      { route: "/companies/999/details" },
    );
    expect(await screen.findByText("Company not found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
