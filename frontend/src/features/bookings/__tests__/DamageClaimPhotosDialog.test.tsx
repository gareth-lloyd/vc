import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/msw/server";
import { drfPage } from "@/test/drf";
import { renderWithProviders } from "@/test/render";
import { DamageClaimPhotosDialog } from "../components/DamageClaimPhotosDialog";
import type { DamageClaim, DamageClaimPhoto } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;
const CLAIM_ID = 7;

function makePhoto(overrides: Partial<DamageClaimPhoto> = {}): DamageClaimPhoto {
  return {
    id: 1,
    image_url: "/media/damage_claims/2026/06/evidence.png",
    caption: "Cracked tile",
    created_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

function makeClaim(photos: DamageClaimPhoto[]): DamageClaim {
  return {
    id: CLAIM_ID,
    reference: "DC-000007",
    booking: BOOKING_ID,
    amount: "500.00",
    description: "Broken window",
    status: "open",
    currency: 1,
    currency_code: "GBP",
    itemized_lines: [],
    photos,
    accepted_by_guest_at: null,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
  };
}

function listHandler(photos: DamageClaimPhoto[]) {
  return http.get(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
    HttpResponse.json(drfPage([makeClaim(photos)])),
  );
}

function setup(canWrite = true) {
  return renderWithProviders(
    <DamageClaimPhotosDialog
      bookingId={BOOKING_ID}
      claimId={CLAIM_ID}
      claimReference="DC-000007"
      canWrite={canWrite}
      open
      onOpenChange={() => {}}
    />,
  );
}

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

describe("DamageClaimPhotosDialog", () => {
  it("renders thumbnails from the claim's embedded photos", async () => {
    server.use(listHandler([makePhoto()]));
    setup();

    const img = await screen.findByRole("img", { name: "Cracked tile" });
    expect(img).toHaveAttribute("src", "/media/damage_claims/2026/06/evidence.png");
    expect(screen.getByText("Cracked tile")).toBeInTheDocument();
  });

  it("shows an empty state with no photos", async () => {
    server.use(listHandler([]));
    setup();

    expect(await screen.findByText(/no photos yet/i)).toBeInTheDocument();
  });

  it("uploads a photo as multipart with the caption and refreshes the grid", async () => {
    let uploaded = false;
    const seen: { contentType: string; caption: FormDataEntryValue | null }[] = [];
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
        HttpResponse.json(drfPage([makeClaim(uploaded ? [makePhoto({ caption: "New" })] : [])])),
      ),
      http.post(
        `/api/v1/bookings/${BOOKING_ID}/damage-claims/${CLAIM_ID}/photos`,
        async ({ request }) => {
          const form = await request.formData();
          seen.push({
            contentType: request.headers.get("content-type") ?? "",
            caption: form.get("caption"),
          });
          uploaded = true;
          return HttpResponse.json(makePhoto({ id: 2, caption: "New" }), { status: 201 });
        },
      ),
    );
    setup();

    await screen.findByText(/no photos yet/i);
    await userEvent.type(screen.getByLabelText(/photo caption/i), "New");
    const file = new File(["bytes"], "evidence.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText(/upload a photo/i), file);

    expect(await screen.findByText("New")).toBeInTheDocument();
    // Multipart boundary set by the browser (Content-Type omitted client-side),
    // and the caption rides in the same form body.
    expect(seen[0].contentType).toContain("multipart/form-data");
    expect(seen[0].caption).toBe("New");
  });

  it("deletes a photo", async () => {
    let deleted = false;
    server.use(
      http.get(`/api/v1/bookings/${BOOKING_ID}/damage-claims`, () =>
        HttpResponse.json(drfPage([makeClaim(deleted ? [] : [makePhoto()])])),
      ),
      http.delete(`/api/v1/bookings/${BOOKING_ID}/damage-claims/${CLAIM_ID}/photos/1`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    setup();

    await userEvent.click(await screen.findByRole("button", { name: /delete photo 1/i }));
    await waitFor(() => expect(screen.queryByRole("img", { name: "Cracked tile" })).toBeNull());
  });

  it("hides upload + delete without the write role but still lists", async () => {
    server.use(listHandler([makePhoto()]));
    setup(false);

    expect(await screen.findByRole("img", { name: "Cracked tile" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/upload a photo/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete photo 1/i })).not.toBeInTheDocument();
  });

  it("shows an inline error when the upload is rejected (oversize 4xx)", async () => {
    server.use(
      listHandler([]),
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims/${CLAIM_ID}/photos`, () =>
        HttpResponse.json(
          {
            code: "validation_error",
            detail: "Validation failed",
            field_errors: { image: ["Image is too large; the maximum is 10485760."] },
          },
          { status: 400 },
        ),
      ),
    );
    setup();

    await screen.findByText(/no photos yet/i);
    const file = new File(["bytes"], "big.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText(/upload a photo/i), file);

    expect(await screen.findByText(/image is too large/i)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("toasts on a 5xx upload failure", async () => {
    server.use(
      listHandler([]),
      http.post(`/api/v1/bookings/${BOOKING_ID}/damage-claims/${CLAIM_ID}/photos`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    setup();

    await screen.findByText(/no photos yet/i);
    const file = new File(["bytes"], "evidence.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText(/upload a photo/i), file);

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
