import { describe, expect, it } from "vitest";
import { normalizeEmail, validateAuth, validateEmail } from "./auth";
const valid = {
  username: "alice1",
  display_name: "艾莉丝",
  password: "a safe password",
  email: "alice@example.com",
  code: "123456",
};
describe("auth form validation", () => {
  it("requires a usable username, verified-email code and a sufficiently long password for registration", () => {
    const errors = validateAuth("register", {
      ...valid,
      username: "艾莉丝",
      password: "short",
      code: "123",
    });
    expect(errors.username).toBeTruthy();
    expect(errors.password).toBeTruthy();
    expect(errors.code).toBeTruthy();
  });
  it("requires a display name and accepts only up to 12 allowed characters", () => {
    expect(validateAuth("register", valid)).toEqual({});
    expect(
      validateAuth("register", { ...valid, display_name: "" }).display_name,
    ).toBeTruthy();
    expect(
      validateAuth("register", { ...valid, display_name: "中文English12!@" })
        .display_name,
    ).toBeTruthy();
    expect(
      validateAuth("register", { ...valid, display_name: "中文ABC12!@#$" }),
    ).toEqual({});
    expect(
      validateAuth("register", { ...valid, display_name: "name with space" })
        .display_name,
    ).toBeTruthy();
  });
  it("rejects passwords longer than 128 characters", () => {
    expect(
      validateAuth("register", { ...valid, password: "x".repeat(129) })
        .password,
    ).toBeTruthy();
  });
  it("only requires the selected login method, without imposing registration rules on existing passwords", () => {
    expect(
      validateAuth("password", {
        ...valid,
        password: "old",
        email: "",
        code: "",
      }),
    ).toEqual({});
    expect(
      validateAuth("email", { ...valid, username: "", password: "" }),
    ).toEqual({});
    expect(
      validateAuth("email", { ...valid, code: "12a456" }).code,
    ).toBeTruthy();
  });
  it("normalizes email for delivery and refuses malformed addresses before requesting a code", () => {
    expect(normalizeEmail(" Alice@Example.COM ")).toBe("alice@example.com");
    expect(validateEmail("alice@")).toBeTruthy();
    expect(validateEmail("alice example.com")).toBeTruthy();
    expect(validateEmail(valid.email)).toBeUndefined();
  });
});
