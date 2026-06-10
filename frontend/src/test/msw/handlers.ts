import { http, HttpResponse } from "msw";

export const defaultHandlers = [
  http.get("/api/v1/auth/me", () =>
    HttpResponse.json({ detail: "Unauthenticated" }, { status: 401 }),
  ),
  // BootGate fires this on every mount (CSRF cookie prime); always-on so
  // unrelated tests don't trip onUnhandledRequest.
  http.get("/api/v1/auth/csrf", () => new HttpResponse(null, { status: 204 })),
];

// The block dialogs read a property's calendar to grey out occupied days in the
// range picker. Install these in dialog tests that open the picker but don't care
// about availability; tests that do care override with server.use(). Kept out of
// the always-on defaults so an unrelated test that unexpectedly hits a calendar
// endpoint still trips MSW's onUnhandledRequest:"error" safety net.
export const blockCalendarHandlers = [
  http.get("/api/v1/properties/:id/availability", ({ params }) =>
    HttpResponse.json({ property_id: Number(params.id), cells: [] }),
  ),
  http.get("/api/v1/owner/properties/:id/calendar", ({ params }) =>
    HttpResponse.json({ property_id: Number(params.id), can_request_block: true, cells: [] }),
  ),
];
