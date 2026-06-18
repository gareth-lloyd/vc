import { describe, expect, it } from "vitest";
import {
  contactCreateInputSchema,
  contactEmailWriteInputSchema,
  contactPhoneWriteInputSchema,
  contactWriteInputSchema,
} from "../schemas";

describe("contactEmailWriteInputSchema", () => {
  it("accepts a valid email", () => {
    const result = contactEmailWriteInputSchema.parse({
      email: "test@example.com",
      label: "work",
    });
    expect(result.email).toBe("test@example.com");
  });

  it("rejects an invalid email", () => {
    expect(() => contactEmailWriteInputSchema.parse({ email: "not-an-email" })).toThrow(
      /valid email/i,
    );
  });

  it("enforces max-length on email", () => {
    expect(() =>
      contactEmailWriteInputSchema.parse({ email: `${"a".repeat(250)}@test.com` }),
    ).toThrow();
  });
});

describe("contactPhoneWriteInputSchema", () => {
  it("accepts a valid phone", () => {
    const result = contactPhoneWriteInputSchema.parse({ number: "+34 600 123 456" });
    expect(result.number).toBe("+34 600 123 456");
  });

  it("rejects empty phone number", () => {
    expect(() => contactPhoneWriteInputSchema.parse({ number: "" })).toThrow(/required/i);
  });

  it("enforces max-length on number", () => {
    expect(() => contactPhoneWriteInputSchema.parse({ number: "1".repeat(41) })).toThrow();
  });
});

describe("contactWriteInputSchema", () => {
  it("accepts a contact with first_name only", () => {
    const result = contactWriteInputSchema.parse({ first_name: "Alice" });
    expect(result.first_name).toBe("Alice");
  });

  it("accepts a contact with company only", () => {
    const result = contactWriteInputSchema.parse({ company: "Acme Ltd" });
    expect(result.company).toBe("Acme Ltd");
  });

  it("rejects a contact with no name or company", () => {
    expect(() => contactWriteInputSchema.parse({})).toThrow(/name or company/i);
  });

  it("trims whitespace from fields", () => {
    const result = contactWriteInputSchema.parse({ first_name: "  Alice  " });
    expect(result.first_name).toBe("Alice");
  });
});

describe("contactCreateInputSchema", () => {
  it("accepts a contact with a name and an email", () => {
    const result = contactCreateInputSchema.parse({
      first_name: "Alice",
      email: "alice@example.com",
    });
    expect(result.email).toBe("alice@example.com");
  });

  it("accepts a contact with a name and a phone", () => {
    const result = contactCreateInputSchema.parse({
      first_name: "Alice",
      phone: "+34 600 123 456",
    });
    expect(result.phone).toBe("+34 600 123 456");
  });

  it("rejects a contact with no channel", () => {
    expect(() => contactCreateInputSchema.parse({ first_name: "Alice" })).toThrow(/reachable/i);
  });

  it("rejects a contact with no name or company", () => {
    expect(() => contactCreateInputSchema.parse({ email: "alice@example.com" })).toThrow(
      /name or company/i,
    );
  });

  it("rejects an invalid email when one is supplied", () => {
    expect(() =>
      contactCreateInputSchema.parse({ first_name: "Alice", email: "not-an-email" }),
    ).toThrow(/valid email/i);
  });
});
