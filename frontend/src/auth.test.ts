import { describe, expect, it } from "vitest";
import { normalizeEmail, validateAuth, validateEmail } from "./auth";
const valid = { username: "alice_1", display_name: "", password: "a safe password", email: "alice@example.com", code: "123456" };
describe("auth form validation", () => {
  it("requires a usable username, verified-email code and a sufficiently long password for registration", () => {
    const errors = validateAuth("register", { ...valid, username: "a@", password: "short", code: "123" });
    expect(errors.username).toBeTruthy(); expect(errors.password).toBeTruthy(); expect(errors.code).toBeTruthy();
  });
  it("allows optional display name but rejects oversized Unicode names and passwords", () => {
    expect(validateAuth("register", valid)).toEqual({});
    expect(validateAuth("register", { ...valid, display_name: "沐".repeat(81), password: "x".repeat(129) })).toMatchObject({ display_name: expect.any(String), password: expect.any(String) });
  });
  it("only requires the selected login method, without imposing registration rules on existing passwords", () => {
    expect(validateAuth("password", { ...valid, password: "old", email: "", code: "" })).toEqual({});
    expect(validateAuth("email", { ...valid, username: "", password: "" })).toEqual({});
    expect(validateAuth("email", { ...valid, code: "12a456" }).code).toBeTruthy();
  });
  it("normalizes email for delivery and refuses malformed addresses before requesting a code", () => {
    expect(normalizeEmail(" Alice@Example.COM ")).toBe("alice@example.com");
    expect(validateEmail("alice@" )).toBeTruthy();
    expect(validateEmail("alice example.com")).toBeTruthy();
    expect(validateEmail(valid.email)).toBeUndefined();
  });
});
