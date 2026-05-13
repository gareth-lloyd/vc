import { http, HttpResponse } from "msw";

export const defaultHandlers = [
  http.get("/api/v1/auth/me", () =>
    HttpResponse.json({ detail: "Unauthenticated" }, { status: 401 }),
  ),
];
