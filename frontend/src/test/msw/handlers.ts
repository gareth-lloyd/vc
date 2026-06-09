import { http, HttpResponse } from "msw";

export const defaultHandlers = [
  http.get("/api/v1/auth/me", () =>
    HttpResponse.json({ detail: "Unauthenticated" }, { status: 401 }),
  ),
  // The block dialogs read the calendar to grey out occupied days. Default to an
  // empty calendar so dialog tests that don't care about availability don't have
  // to mock it; tests that do care override with server.use().
  http.get("/api/v1/properties/:id/availability", ({ params }) =>
    HttpResponse.json({ property_id: Number(params.id), cells: [] }),
  ),
  http.get("/api/v1/owner/properties/:id/calendar", ({ params }) =>
    HttpResponse.json({ property_id: Number(params.id), can_request_block: true, cells: [] }),
  ),
];
