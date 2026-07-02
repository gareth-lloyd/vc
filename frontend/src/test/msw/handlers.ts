import { http, HttpResponse } from "msw";
import { drfPage } from "@/test/drf";

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

// Geo lookup lists behind the country/region filter dropdowns (quote builder,
// properties list). Install in tests that mount those screens but don't care
// about the option lists; tests that do care override with server.use().
// Same opt-in rationale as blockCalendarHandlers above.
export const geoLookupHandlers = [
  http.get("/api/v1/countries", () =>
    HttpResponse.json(
      drfPage([
        { id: 1, iso2: "ES", name: "Spain", is_active: true },
        { id: 2, iso2: "GR", name: "Greece", is_active: true },
      ]),
    ),
  ),
  http.get("/api/v1/regions", () =>
    HttpResponse.json(
      drfPage([
        { id: 7, country: 1, country_iso2: "ES", name: "Ibiza", slug: "ibiza" },
        { id: 11, country: 2, country_iso2: "GR", name: "Crete", slug: "crete" },
      ]),
    ),
  ),
];
