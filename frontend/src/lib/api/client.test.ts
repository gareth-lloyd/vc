import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/msw/server";
import { ApiError } from "./errors";
import { authChannel } from "./authChannel";
import { apiGet, apiSend } from "./client";

const setCookie = (value: string) => {
  document.cookie = value;
};

const clearCookies = () => {
  // jsdom: setting an expired cookie clears it
  for (const part of document.cookie.split(";")) {
    const name = part.split("=")[0].trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  }
};

beforeEach(() => {
  clearCookies();
});

afterEach(() => {
  clearCookies();
});

describe("apiGet", () => {
  it("returns parsed JSON on 200", async () => {
    server.use(http.get("/api/v1/foo", () => HttpResponse.json({ ok: true })));
    const result = await apiGet<{ ok: boolean }>("/foo");
    expect(result).toEqual({ ok: true });
  });

  it("sends credentials and Accept header", async () => {
    const seen: { credentials?: string; accept?: string | null } = {};
    server.use(
      http.get("/api/v1/foo", ({ request }) => {
        seen.accept = request.headers.get("accept");
        return HttpResponse.json({});
      }),
    );
    await apiGet("/foo");
    expect(seen.accept).toContain("application/json");
  });

  it("throws ApiError on 400 with field_errors", async () => {
    server.use(
      http.get("/api/v1/foo", () =>
        HttpResponse.json(
          { code: "invalid", detail: "Bad input", field_errors: { email: ["required"] } },
          { status: 400 },
        ),
      ),
    );
    await expect(apiGet("/foo")).rejects.toMatchObject({
      status: 400,
      code: "invalid",
      detail: "Bad input",
      fieldErrors: { email: ["required"] },
    });
  });

  it("emits unauthorized event on 401", async () => {
    server.use(http.get("/api/v1/foo", () => HttpResponse.json({}, { status: 401 })));
    const handler = vi.fn();
    const unsubscribe = authChannel.onUnauthorized(handler);
    try {
      await expect(apiGet("/foo")).rejects.toBeInstanceOf(ApiError);
      expect(handler).toHaveBeenCalledOnce();
    } finally {
      unsubscribe();
    }
  });
});

describe("apiSend", () => {
  it("sends X-CSRFToken from csrftoken cookie on unsafe verbs", async () => {
    setCookie("csrftoken=ABC123");
    let observed: string | null = null;
    server.use(
      http.post("/api/v1/things", ({ request }) => {
        observed = request.headers.get("x-csrftoken");
        return HttpResponse.json({ id: 1 });
      }),
    );
    const result = await apiSend<{ id: number }>("POST", "/things", { name: "x" });
    expect(observed).toBe("ABC123");
    expect(result).toEqual({ id: 1 });
  });

  it("returns undefined on 204", async () => {
    setCookie("csrftoken=ABC123");
    server.use(http.delete("/api/v1/things/1", () => new HttpResponse(null, { status: 204 })));
    const result = await apiSend("DELETE", "/things/1");
    expect(result).toBeUndefined();
  });

  it("serialises JSON body and sets Content-Type", async () => {
    setCookie("csrftoken=ABC123");
    let payload: unknown;
    let contentType: string | null = null;
    server.use(
      http.post("/api/v1/things", async ({ request }) => {
        contentType = request.headers.get("content-type");
        payload = await request.json();
        return HttpResponse.json({});
      }),
    );
    await apiSend("POST", "/things", { name: "x" });
    expect(contentType).toContain("application/json");
    expect(payload).toEqual({ name: "x" });
  });
});
