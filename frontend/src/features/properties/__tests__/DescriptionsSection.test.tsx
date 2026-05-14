import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { drfPage } from "@/test/drf";
import { useAuthStore } from "@/features/auth/store";
import { DescriptionsSection } from "../components/DescriptionsSection";

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

const overviewRecord = {
  id: 1,
  property: 7,
  section: "overview",
  body: "Welcome to Casa Sur.",
  updated_at: "2026-05-01T00:00:00Z",
};

describe("DescriptionsSection", () => {
  it("loads existing overview body into the textarea", async () => {
    setReservationsUser();
    server.use(
      http.get("/api/v1/properties/7/descriptions", () =>
        HttpResponse.json(drfPage([overviewRecord])),
      ),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);
    const textarea = (await screen.findByPlaceholderText(
      /Write the section content here/i,
    )) as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe("Welcome to Casa Sur."));
    useAuthStore.getState().clear();
  });

  it("PUTs the upsert endpoint with hyphenated slug for house_rules", async () => {
    setReservationsUser();
    server.use(http.get("/api/v1/properties/7/descriptions", () => HttpResponse.json(drfPage([]))));
    let putBody: { body?: string } | null = null;
    server.use(
      http.put("/api/v1/properties/7/descriptions/house-rules", async ({ request }) => {
        putBody = (await request.json()) as { body?: string };
        return HttpResponse.json(
          { id: 2, property: 7, section: "house_rules", body: putBody?.body ?? "" },
          { status: 201 },
        );
      }),
    );
    renderWithProviders(<DescriptionsSection propertyId={7} />);
    await userEvent.click(await screen.findByRole("tab", { name: /house rules/i }));
    const textarea = await screen.findByPlaceholderText(/Write the section content here/i);
    await userEvent.type(textarea, "No smoking.");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody!.body).toBe("No smoking.");
    useAuthStore.getState().clear();
  });
});
