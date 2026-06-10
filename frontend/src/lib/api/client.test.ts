import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/msw/server";
import { ApiError } from "./errors";
import { authChannel } from "./authChannel";
import { apiGet, apiSend, primeCsrfCookie } from "./client";

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

describe("primeCsrfCookie", () => {
  it("returns true on 204", async () => {
    server.use(http.get("/api/v1/auth/csrf", () => new HttpResponse(null, { status: 204 })));
    await expect(primeCsrfCookie()).resolves.toBe(true);
  });

  it("returns false on a 401 without tripping the auth channel", async () => {
    // e.g. a basic-auth-protected staging proxy; a background prime must
    // never flip the app's auth state.
    server.use(http.get("/api/v1/auth/csrf", () => HttpResponse.json({}, { status: 401 })));
    const handler = vi.fn();
    const unsubscribe = authChannel.onUnauthorized(handler);
    try {
      await expect(primeCsrfCookie()).resolves.toBe(false);
      expect(handler).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });

  it("returns false on network error without throwing", async () => {
    server.use(http.get("/api/v1/auth/csrf", () => HttpResponse.error()));
    await expect(primeCsrfCookie()).resolves.toBe(false);
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

  it("primes the cookie and replays once when CsrfViewMiddleware rejects (non-JSON 403)", async () => {
    // Fresh browser racing the boot prime: no csrftoken cookie yet.
    let posts = 0;
    let primes = 0;
    let tokenOnReplay: string | null = null;
    server.use(
      http.get("/api/v1/auth/csrf", () => {
        primes += 1;
        setCookie("csrftoken=FRESH"); // what the browser would do with Set-Cookie
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("/api/v1/things", ({ request }) => {
        posts += 1;
        if (request.headers.get("x-csrftoken") !== "FRESH") {
          return new HttpResponse("<html>CSRF verification failed</html>", {
            status: 403,
            headers: { "Content-Type": "text/html" },
          });
        }
        tokenOnReplay = request.headers.get("x-csrftoken");
        return HttpResponse.json({ id: 1 });
      }),
    );

    const result = await apiSend<{ id: number }>("POST", "/things", { name: "x" });

    expect(result).toEqual({ id: 1 });
    expect(primes).toBe(1);
    expect(posts).toBe(2);
    expect(tokenOnReplay).toBe("FRESH");
  });

  it("replays a CSRF-rejected request at most once", async () => {
    let posts = 0;
    server.use(
      http.get("/api/v1/auth/csrf", () => new HttpResponse(null, { status: 204 })),
      http.post("/api/v1/things", () => {
        posts += 1;
        return new HttpResponse("<html>CSRF verification failed</html>", {
          status: 403,
          headers: { "Content-Type": "text/html" },
        });
      }),
    );

    await expect(apiSend("POST", "/things", { name: "x" })).rejects.toMatchObject({
      status: 403,
    });
    expect(posts).toBe(2);
  });

  it("does not replay a JSON 403 (real permission denial)", async () => {
    setCookie("csrftoken=ABC123");
    let posts = 0;
    server.use(
      http.post("/api/v1/things", () => {
        posts += 1;
        return HttpResponse.json({ code: "forbidden", detail: "Nope" }, { status: 403 });
      }),
    );

    await expect(apiSend("POST", "/things", { name: "x" })).rejects.toMatchObject({
      status: 403,
      code: "forbidden",
    });
    expect(posts).toBe(1);
  });

  it("does not replay when the prime itself fails", async () => {
    let posts = 0;
    server.use(
      http.get("/api/v1/auth/csrf", () => new HttpResponse(null, { status: 500 })),
      http.post("/api/v1/things", () => {
        posts += 1;
        return new HttpResponse("<html>CSRF verification failed</html>", {
          status: 403,
          headers: { "Content-Type": "text/html" },
        });
      }),
    );

    await expect(apiSend("POST", "/things", { name: "x" })).rejects.toMatchObject({
      status: 403,
    });
    expect(posts).toBe(1);
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
