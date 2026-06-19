import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { LeadStatusCell } from "../components/LeadStatusCell";

const baseUser = {
  id: 1,
  email: "writer@example.com",
  first_name: "Wri",
  last_name: "Ter",
  is_active: true,
  is_staff: true,
  is_superuser: false,
  preferred_language: "en",
};

function grantWriterRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: "RESERVATIONS" },
    role: "RESERVATIONS",
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

function clearRole() {
  useAuthStore.setState({
    user: { ...baseUser, role: null },
    role: null,
    isSuperuser: false,
    permissions: [],
    status: "authenticated",
    pendingTfa: null,
  });
}

const detailFixture = {
  id: 1,
  reference: "E-AAA-001",
  status: "new",
  adults: 2,
  request_type: "quote",
  site_source: "main_website",
  lead_status: "warm",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LeadStatusCell", () => {
  it("renders a read-only badge without the reservations role", () => {
    clearRole();
    renderWithProviders(<LeadStatusCell enquiryId={1} reference="E-AAA-001" value="hot" />);

    expect(screen.getByText("Hot")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("does not bubble the trigger click to the row (stopPropagation guard)", async () => {
    grantWriterRole();
    const onRowClick = vi.fn();
    renderWithProviders(
      <div onClick={onRowClick}>
        <LeadStatusCell enquiryId={1} reference="E-AAA-001" value="warm" />
      </div>,
    );

    await userEvent.click(screen.getByRole("button", { name: /change lead status/i }));

    // The picker opened…
    expect(await screen.findByText("Set lead status")).toBeInTheDocument();
    // …without triggering the row's navigation handler.
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("posts the chosen lead status via the audited action", async () => {
    grantWriterRole();
    let body: unknown = null;
    server.use(
      http.post("/api/v1/enquiries/1:set-lead-status", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...detailFixture, lead_status: "hot" });
      }),
    );
    renderWithProviders(<LeadStatusCell enquiryId={1} reference="E-AAA-001" value="warm" />);

    await userEvent.click(screen.getByRole("button", { name: /change lead status/i }));
    await userEvent.click(screen.getByRole("button", { name: /^hot$/i }));

    await waitFor(() => expect(body).toEqual({ lead_status: "hot" }));
  });

  it("shows a toast on a 5xx", async () => {
    grantWriterRole();
    const errorSpy = vi.spyOn(toast, "error");
    server.use(
      http.post("/api/v1/enquiries/1:set-lead-status", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    renderWithProviders(<LeadStatusCell enquiryId={1} reference="E-AAA-001" value="warm" />);

    await userEvent.click(screen.getByRole("button", { name: /change lead status/i }));
    await userEvent.click(screen.getByRole("button", { name: /^cold$/i }));

    await waitFor(() => expect(errorSpy).toHaveBeenCalled());
  });
});
