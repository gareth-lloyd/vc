import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, waitFor, within } from "@testing-library/react";
import i18n from "@/i18n";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/render";
import { Topbar, type TopbarUser } from "../Topbar";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const USER: TopbarUser = {
  email: "alex@example.com",
  first_name: "Alex",
  last_name: "Doe",
};

function userMePayload(language: string) {
  return {
    id: 1,
    email: USER.email,
    first_name: USER.first_name,
    last_name: USER.last_name,
    is_active: true,
    is_staff: true,
    is_superuser: false,
    preferred_language: language,
  };
}

async function openLanguageMenu() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /alex@example\.com/i }));
  return { user, menu: await screen.findByRole("menu") };
}

beforeEach(async () => {
  vi.mocked(toast.error).mockClear();
  await i18n.changeLanguage("en");
});

afterEach(() => {
  server.resetHandlers();
});

describe("Topbar", () => {
  it("renders a language radio group with the current language checked", async () => {
    renderWithProviders(<Topbar user={USER} onSignOut={() => {}} />);
    const { menu } = await openLanguageMenu();

    expect(within(menu).getByRole("menuitemradio", { name: "English" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(within(menu).getByRole("menuitemradio", { name: "Ελληνικά" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("does not fire PATCH /auth/me when the user reselects the current language", async () => {
    let patchCount = 0;
    server.use(
      http.patch("/api/v1/auth/me", () => {
        patchCount += 1;
        return HttpResponse.json(userMePayload("en"));
      }),
    );

    renderWithProviders(<Topbar user={USER} onSignOut={() => {}} />);
    const { user, menu } = await openLanguageMenu();
    await user.click(within(menu).getByRole("menuitemradio", { name: "English" }));

    expect(patchCount).toBe(0);
  });

  it("PATCHes preferred_language and switches i18next on selecting a new language", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.patch("/api/v1/auth/me", async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(userMePayload("el"));
      }),
    );

    renderWithProviders(<Topbar user={USER} onSignOut={() => {}} />);
    const { user, menu } = await openLanguageMenu();
    await user.click(within(menu).getByRole("menuitemradio", { name: "Ελληνικά" }));

    await waitFor(() => expect(receivedBody).toEqual({ preferred_language: "el" }));
    expect(i18n.language).toBe("el");
    expect(vi.mocked(toast.error)).not.toHaveBeenCalled();
  });

  it("reverts i18next and toasts when PATCH /auth/me fails", async () => {
    server.use(
      http.patch("/api/v1/auth/me", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );

    renderWithProviders(<Topbar user={USER} onSignOut={() => {}} />);
    const { user, menu } = await openLanguageMenu();
    await user.click(within(menu).getByRole("menuitemradio", { name: "Ελληνικά" }));

    await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalledTimes(1));
    expect(i18n.language).toBe("en");
  });
});
