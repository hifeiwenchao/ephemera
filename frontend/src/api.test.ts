import { afterEach, describe, expect, it, vi } from "vitest";
import { searchUsers } from "./api";

afterEach(() => vi.unstubAllGlobals());
describe("API identity and errors", () => {
  it("encodes a username and sends the active demo identity", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ id: 2, username: "bob" }]), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const users = await searchUsers(7, "bo &");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/users/search?q=bo%20%26");
    expect(
      new Headers(fetchMock.mock.calls[0][1].headers).get("X-User-Id"),
    ).toBe("7");
    expect(users[0].username).toBe("bob");
  });
  it("surfaces the server error without pretending success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "unavailable", message: "服务暂不可用" },
          }),
          { status: 503 },
        ),
      ),
    );
    await expect(searchUsers(1, "bo")).rejects.toThrow("服务暂不可用");
  });
});
