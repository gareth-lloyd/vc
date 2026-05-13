import { describe, expect, it } from "vitest";
import {
  loginInputSchema,
  loginResponseSchema,
  permissionsResponseSchema,
  userMeSchema,
} from "../schemas";

describe("loginInputSchema", () => {
  it("accepts a valid login input", () => {
    expect(loginInputSchema.safeParse({ email: "a@b.com", password: "secret" }).success).toBe(true);
  });

  it("rejects bad email", () => {
    expect(loginInputSchema.safeParse({ email: "nope", password: "secret" }).success).toBe(false);
  });

  it("rejects empty password", () => {
    expect(loginInputSchema.safeParse({ email: "a@b.com", password: "" }).success).toBe(false);
  });
});

describe("userMeSchema", () => {
  it("parses a real-shape /auth/me response", () => {
    const fixture = {
      id: 7,
      email: "ops@vc.test",
      first_name: "Gareth",
      last_name: "Lloyd",
      phone: null,
      role: "operator",
      is_active: true,
      is_staff: true,
      is_superuser: false,
      tfa_method: null,
      tfa_enrolled_at: null,
      last_login: "2026-05-13T10:00:00Z",
    };
    expect(userMeSchema.parse(fixture).email).toBe("ops@vc.test");
  });
});

describe("loginResponseSchema", () => {
  it("accepts non-tfa shape", () => {
    const ok = loginResponseSchema.safeParse({
      tfa_required: false,
      user: {
        id: 1,
        email: "a@b.com",
        first_name: "A",
        last_name: "B",
        is_active: true,
        is_staff: true,
        is_superuser: false,
      },
    });
    expect(ok.success).toBe(true);
  });

  it("accepts tfa shape", () => {
    const ok = loginResponseSchema.safeParse({
      tfa_required: true,
      challenge_token: "tok",
      expires_in_seconds: 300,
    });
    expect(ok.success).toBe(true);
  });
});

describe("permissionsResponseSchema", () => {
  it("parses the permissions endpoint shape", () => {
    expect(
      permissionsResponseSchema.parse({
        role: "operator",
        is_superuser: false,
        permissions: ["properties.view_property"],
      }).permissions,
    ).toContain("properties.view_property");
  });
});
