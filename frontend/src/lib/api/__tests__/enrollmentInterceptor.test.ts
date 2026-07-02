import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/msw/server";
import { apiGet } from "../client";
import { authChannel } from "../authChannel";
import { ApiError } from "../errors";

describe("client 403 tfa_enrollment_required interceptor", () => {
  afterEach(() => vi.restoreAllMocks());

  it("emits emitEnrollmentRequired (not unauthorized) and still throws", async () => {
    const onEnroll = vi.fn();
    const onUnauth = vi.fn();
    const offEnroll = authChannel.onEnrollmentRequired(onEnroll);
    const offUnauth = authChannel.onUnauthorized(onUnauth);
    server.use(
      http.get("/api/v1/anything", () =>
        HttpResponse.json(
          { code: "tfa_enrollment_required", detail: "Set up 2FA.", field_errors: {} },
          { status: 403 },
        ),
      ),
    );

    await expect(apiGet("/anything")).rejects.toBeInstanceOf(ApiError);
    expect(onEnroll).toHaveBeenCalledTimes(1);
    expect(onUnauth).not.toHaveBeenCalled();

    offEnroll();
    offUnauth();
  });

  it("does not emit on an ordinary 403 (e.g. forbidden)", async () => {
    const onEnroll = vi.fn();
    const offEnroll = authChannel.onEnrollmentRequired(onEnroll);
    server.use(
      http.get("/api/v1/anything", () =>
        HttpResponse.json({ code: "forbidden", detail: "No.", field_errors: {} }, { status: 403 }),
      ),
    );

    await expect(apiGet("/anything")).rejects.toBeInstanceOf(ApiError);
    expect(onEnroll).not.toHaveBeenCalled();

    offEnroll();
  });
});
