import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { openDateRange, typeDateRange } from "@/test/dateRange";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { ServiceFormDialog } from "../components/ServiceFormDialog";
import type { PropertyService } from "../schemas";

function setReservationsUser() {
  useAuthStore.getState().setMe(
    {
      id: 1,
      email: "a@test.com",
      first_name: "A",
      last_name: "T",
      is_active: true,
      is_staff: true,
      is_superuser: false,
      preferred_language: "en",
      role: "RESERVATIONS",
    },
    { role: "RESERVATIONS", is_superuser: false, permissions: [] },
  );
}

describe("ServiceFormDialog — create", () => {
  it("posts name + copy and omits empty date bands", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/properties/7/services", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 42,
            property: 7,
            name: postBody.name,
            copy: postBody.copy,
            notes: postBody.notes ?? null,
            applies_from: postBody.applies_from ?? null,
            applies_to: postBody.applies_to ?? null,
            sort_order: 0,
            is_active: true,
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(
      <ServiceFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );

    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Private chef");
    await userEvent.type(screen.getByLabelText(/Guest-facing copy/i), "Chef prepares dinner.");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({ name: "Private chef", copy: "Chef prepares dinner." });
    // Empty date inputs are sent as explicit null (open-ended band), never as ""
    // which the API rejects as an invalid date.
    expect(postBody!.applies_from).toBeNull();
    expect(postBody!.applies_to).toBeNull();
    useAuthStore.getState().clear();
  });

  it("blocks save and never POSTs when guest copy is empty", async () => {
    setReservationsUser();
    let postCalled = false;
    server.use(
      http.post("/api/v1/properties/7/services", () => {
        postCalled = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderWithProviders(
      <ServiceFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );

    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Private chef");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    // The required-copy Zod message surfaces inline; the POST is never fired.
    expect(await screen.findByText(/Guest-facing copy is required/i)).toBeInTheDocument();
    expect(postCalled).toBe(false);
    useAuthStore.getState().clear();
  });

  it("surfaces a 400 field error inline and the detail as a top-level alert", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/properties/7/services", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { name: ["A service with this name already exists."] },
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(
      <ServiceFormDialog propertyId={7} open mode="create" onOpenChange={() => {}} />,
    );

    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Private chef");
    await userEvent.type(screen.getByLabelText(/Guest-facing copy/i), "Chef prepares dinner.");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    expect(screen.getByText(/Validation failed/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });
});

describe("ServiceFormDialog — edit", () => {
  it("PATCHes the flat service route with edited fields", async () => {
    setReservationsUser();
    const service: PropertyService = {
      id: 300,
      property: 7,
      name: "Private chef",
      copy: "Chef prepares dinner.",
      notes: "",
      applies_from: "2026-06-01",
      applies_to: "2026-08-31",
      sort_order: 0,
      is_active: true,
    };
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/services/300", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...service, name: patchBody.name });
      }),
    );

    renderWithProviders(
      <ServiceFormDialog
        propertyId={7}
        open
        mode="edit"
        service={service}
        onOpenChange={() => {}}
      />,
    );

    const nameInput = (await screen.findByLabelText(/^Name$/i)) as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Private chef"));
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Private chef (summer)");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.name).toBe("Private chef (summer)");
    useAuthStore.getState().clear();
  });

  it("clears a banded service to year-round by PATCHing null dates", async () => {
    setReservationsUser();
    const service: PropertyService = {
      id: 300,
      property: 7,
      name: "Private chef",
      copy: "Chef prepares dinner.",
      notes: "",
      applies_from: "2026-06-01",
      applies_to: "2026-08-31",
      sort_order: 0,
      is_active: true,
    };
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/services/300", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...service, applies_from: null, applies_to: null });
      }),
    );

    renderWithProviders(
      <ServiceFormDialog
        propertyId={7}
        open
        mode="edit"
        service={service}
        onOpenChange={() => {}}
      />,
    );

    // The date band lives behind the DateRangePicker trigger — its typed
    // inputs portal to the popover, so open it before clearing.
    const picker = await openDateRange(userEvent, /^dates/i);
    await waitFor(() => expect(picker.getByLabelText(/^applies from$/i)).toHaveValue("2026-06-01"));
    await typeDateRange(
      userEvent,
      picker,
      { from: "", to: "" },
      { from: /^applies from$/i, to: /^applies to$/i },
    );
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    // Emptied dates must go over the wire as explicit null (not omitted) so the
    // band is actually cleared, converting the service to year-round.
    expect(patchBody!.applies_from).toBeNull();
    expect(patchBody!.applies_to).toBeNull();
    useAuthStore.getState().clear();
  });

  it("PATCHes an open end (null applies_to) when only To is cleared", async () => {
    setReservationsUser();
    const service: PropertyService = {
      id: 300,
      property: 7,
      name: "Private chef",
      copy: "Chef prepares dinner.",
      notes: "",
      applies_from: "2026-06-01",
      applies_to: "2026-08-31",
      sort_order: 0,
      is_active: true,
    };
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/services/300", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...service, applies_from: "2026-05-15", applies_to: null });
      }),
    );

    renderWithProviders(
      <ServiceFormDialog
        propertyId={7}
        open
        mode="edit"
        service={service}
        onOpenChange={() => {}}
      />,
    );

    // Partial window via the popover's typed inputs: retype From, clear To.
    const picker = await openDateRange(userEvent, /^dates/i);
    await typeDateRange(
      userEvent,
      picker,
      { from: "2026-05-15", to: "" },
      { from: /^applies from$/i, to: /^applies to$/i },
    );
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    // From survives as typed; the cleared To crosses the wire as explicit null
    // (open-ended band), never "" which the API rejects as an invalid date.
    expect(patchBody!.applies_from).toBe("2026-05-15");
    expect(patchBody!.applies_to).toBeNull();
    useAuthStore.getState().clear();
  });
});
