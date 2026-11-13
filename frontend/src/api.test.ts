import { afterEach, describe, expect, it, vi } from "vitest";
import { AUTH_EXPIRED_EVENT, ApiError, getMe, loginWithEmail, loginWithPassword, logout, register, searchUsers, sendEmailCode, socketUrl } from "./api";
const user = { id: 9, username: "alice", display_name: "艾莉丝", avatar_url: null };
function mockResponse(data: unknown, status = 200) { const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status })); vi.stubGlobal("fetch", mock); return mock; }
afterEach(() => vi.unstubAllGlobals());
describe("cookie-based authenticated API", () => {
  it("encodes search and includes the session cookie without impersonation headers", async () => {
    const fetchMock = mockResponse([{ ...user, username: "bob" }]);
    const users = await searchUsers(7, "bo &");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/users/search?q=bo%20%26");
    expect(fetchMock.mock.calls[0][1].credentials).toBe("include");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).has("X-User-Id")).toBe(false);
    expect(users[0].username).toBe("bob");
  });
  it.each([
    ["/api/auth/email-code", { email: "alice@example.com", purpose: "register" }, () => sendEmailCode("alice@example.com", "register"), { message: "验证码已发送", retry_after: 60 }],
    ["/api/auth/login/password", { username: "alice", password: " pass word " }, () => loginWithPassword("alice", " pass word "), { user }],
    ["/api/auth/login/email", { email: "alice@example.com", code: "123456" }, () => loginWithEmail("alice@example.com", "123456"), { user }],
    ["/api/auth/register", { username: "alice", display_name: "艾莉丝", password: "password123", email: "alice@example.com", code: "123456" }, () => register({ username: "alice", display_name: "艾莉丝", password: "password123", email: "alice@example.com", code: "123456" }), { user }],
    ["/api/auth/logout", undefined, () => logout(), {}],
  ] as const)("sends %s as a cookie-based JSON request", async (path, payload, action, result) => {
    const fetchMock = mockResponse(result);
    expect(await action()).toEqual(result);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(path); expect(options.method).toBe("POST"); expect(options.credentials).toBe("include");
    expect(options.body ? JSON.parse(String(options.body)) : undefined).toEqual(payload);
  });
  it("announces an expired protected session and preserves the unauthorized error", async () => {
    const dispatchEvent = vi.fn(); vi.stubGlobal("window", { dispatchEvent });
    mockResponse({ error: { code: "unauthorized", message: "请先登录" } }, 401);
    await expect(getMe()).rejects.toMatchObject({ status: 401, message: "请先登录" });
    expect(dispatchEvent.mock.calls[0][0].type).toBe(AUTH_EXPIRED_EVENT);
  });
  it("keeps a failed sign-in distinct from an expired session", async () => {
    const dispatchEvent = vi.fn(); vi.stubGlobal("window", { dispatchEvent });
    mockResponse({ error: { code: "invalid_credentials", message: "用户名或密码不正确" } }, 401);
    await expect(loginWithPassword("alice", "wrong")).rejects.toMatchObject({ status: 401 });
    expect(dispatchEvent).not.toHaveBeenCalled();
  });
  it("distinguishes service failures from loss of authentication", async () => {
    const dispatchEvent = vi.fn(); vi.stubGlobal("window", { dispatchEvent });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network failed")));
    await expect(getMe()).rejects.toMatchObject({ status: 0 });
    expect(dispatchEvent).not.toHaveBeenCalled();
    mockResponse({ error: { code: "unavailable", message: "服务暂不可用" } }, 503);
    await expect(searchUsers(1, "bo")).rejects.toThrow("服务暂不可用");
  });
  it("opens the conversation socket without putting an identity or token in its URL", () => {
    vi.stubGlobal("location", { protocol: "http:", host: "localhost:5173" });
    expect(socketUrl(9, 2)).toBe("ws://localhost:5173/ws/conversations/2");
  });
});

describe("unread API contract", () => {
  it("marks only an explicit rendered message boundary using the session cookie", async () => {
    const api = await import("./api");
    expect(api).toHaveProperty("markConversationRead");
    const fetchMock = mockResponse({ id: 7, unread_count: 0, other_last_read_message_id: null });
    await api.markConversationRead(9, 7, 42);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/conversations/7/read");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(JSON.parse(options.body)).toEqual({ last_message_id: 42 });
  });
  it("opens user-wide events without an identity in the URL", async () => {
    const api = await import("./api");
    expect(api).toHaveProperty("eventsSocketUrl");
    vi.stubGlobal("location", { protocol: "https:", host: "localhost:5173" });
    expect(api.eventsSocketUrl()).toBe("wss://localhost:5173/ws/events");
  });
});
