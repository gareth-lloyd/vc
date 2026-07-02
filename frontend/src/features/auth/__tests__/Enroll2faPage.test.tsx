import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { useAuthStore } from "../store";
import { Enroll2faPage } from "../Enroll2faPage";

const START = {
  secret: "JBSWY3DPEHPK3PXP",
  provisioning_uri: "otpauth://totp/Villa%20Collective:ops@vc.test?secret=JBSWY3DPEHPK3PXP",
  recovery_codes: ["aaaa-1111", "bbbb-2222", "cccc-3333"],
};

/** Branch the single :enroll endpoint on whether a code was posted. */
function enrollHandler() {
  return http.post("/api/v1/auth/2fa:enroll", async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { code?: string };
    if (body?.code) {
      return HttpResponse.json({ enrolled: true, tfa_method: "totp" });
    }
    return HttpResponse.json(START);
  });
}

beforeEach(() => {
  useAuthStore.getState().clear();
});
afterEach(() => {
  useAuthStore.getState().clear();
});

function setup() {
  return renderWithProviders(
    <Routes>
      <Route path="/enroll-2fa" element={<Enroll2faPage />} />
      <Route path="/dashboard" element={<div>Dashboard</div>} />
    </Routes>,
    { route: "/enroll-2fa" },
  );
}

describe("Enroll2faPage", () => {
  it("walks QR → confirm → recovery → into the app", async () => {
    server.use(enrollHandler());
    setup();

    // Step 1: the secret (manual-entry fallback) appears once enrolment starts.
    expect(await screen.findByText(START.secret)).toBeInTheDocument();

    // Step 2: confirm with a 6-digit code.
    await userEvent.type(screen.getByLabelText(/6-digit code/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    // Step 3: recovery codes shown; ack continues into the app.
    expect(await screen.findByText("aaaa-1111")).toBeInTheDocument();
    expect(screen.getByText("cccc-3333")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /saved these/i }));

    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
  });

  it("optimistically flips the store to totp on confirm (no bounce back)", async () => {
    server.use(enrollHandler());
    useAuthStore.getState().setMe({
      id: 1,
      email: "ops@vc.test",
      first_name: "Ops",
      last_name: "User",
      phone: null,
      role: "operator",
      is_active: true,
      is_staff: true,
      is_superuser: false,
      tfa_method: "none",
      tfa_enrolled_at: null,
      last_login: null,
      preferred_language: "en",
    });
    setup();

    await screen.findByText(START.secret);
    await userEvent.type(screen.getByLabelText(/6-digit code/i), "123456");
    await userEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await screen.findByText("aaaa-1111");
    // The store must already read "totp" so the boot redirect can't bounce the
    // user back to /enroll-2fa before /auth/me refetches.
    expect(useAuthStore.getState().user?.tfa_method).toBe("totp");
  });

  it("shows the server error inline on a bad confirm code", async () => {
    server.use(
      http.post("/api/v1/auth/2fa:enroll", async ({ request }) => {
        const body = (await request.json().catch(() => ({}))) as { code?: string };
        if (body?.code) {
          return HttpResponse.json(
            { code: "invalid_tfa_code", detail: "Invalid TOTP code.", field_errors: {} },
            { status: 400 },
          );
        }
        return HttpResponse.json(START);
      }),
    );
    setup();

    await screen.findByText(START.secret);
    await userEvent.type(screen.getByLabelText(/6-digit code/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    expect(await screen.findByText(/invalid totp code/i)).toBeInTheDocument();
    // Still on the confirm step (no recovery codes rendered).
    expect(screen.queryByText("aaaa-1111")).not.toBeInTheDocument();
  });
});
