import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "@/features/auth/store";
import { RateCardFormDialog } from "../components/RateCardFormDialog";
import type { RateCard } from "../schemas";

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

const card: RateCard = {
  id: 5,
  plan: 11,
  name: "Standard",
  description: "",
  min_nights: 3,
  max_nights: 14,
  sort_order: 0,
  is_active: true,
  notes: "",
  rules: [],
};

describe("RateCardFormDialog — create", () => {
  it("posts to /seasons/:id/rate-cards with defaults applied", async () => {
    setReservationsUser();
    let postBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/seasons/11/rate-cards", async ({ request }) => {
        postBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { ...card, id: 99, name: postBody.name, min_nights: postBody.min_nights },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(
      <RateCardFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );

    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Standard");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(postBody).not.toBeNull());
    expect(postBody).toMatchObject({ name: "Standard", min_nights: 1, is_active: true });
    useAuthStore.getState().clear();
  });

  it("requires a name and fires no request", async () => {
    setReservationsUser();
    let requested = false;
    server.use(
      http.post("/api/v1/seasons/11/rate-cards", () => {
        requested = true;
        return HttpResponse.json(card, { status: 201 });
      }),
    );
    renderWithProviders(
      <RateCardFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.click(await screen.findByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
    expect(requested).toBe(false);
    useAuthStore.getState().clear();
  });

  it("rejects max nights below min nights", async () => {
    setReservationsUser();
    renderWithProviders(
      <RateCardFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Standard");
    await userEvent.clear(screen.getByLabelText(/Minimum nights/i));
    await userEvent.type(screen.getByLabelText(/Minimum nights/i), "5");
    await userEvent.type(screen.getByLabelText(/Maximum nights/i), "2");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/can't be below minimum nights/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });

  it("surfaces field errors from a 400 response", async () => {
    setReservationsUser();
    server.use(
      http.post("/api/v1/seasons/11/rate-cards", () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { name: ["This name is already taken."] },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(
      <RateCardFormDialog seasonId={11} open onOpenChange={() => {}} mode="create" />,
    );
    await userEvent.type(await screen.findByLabelText(/^Name$/i), "Standard");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/already taken/i)).toBeInTheDocument();
    useAuthStore.getState().clear();
  });
});

describe("RateCardFormDialog — edit", () => {
  it("prefills from the card and PATCHes edited fields", async () => {
    setReservationsUser();
    let patchBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/rate-cards/5", async ({ request }) => {
        patchBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...card, name: patchBody.name });
      }),
    );

    renderWithProviders(
      <RateCardFormDialog seasonId={11} open onOpenChange={() => {}} mode="edit" card={card} />,
    );

    const nameInput = (await screen.findByLabelText(/^Name$/i)) as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Standard"));
    expect((screen.getByLabelText(/Minimum nights/i) as HTMLInputElement).value).toBe("3");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Premium");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody!.name).toBe("Premium");
    useAuthStore.getState().clear();
  });
});
