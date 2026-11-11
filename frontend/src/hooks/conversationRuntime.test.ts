import { describe, expect, it } from "vitest";
import { mergeMessages } from "../messages";
import type { Message } from "../types";
import { HistoryPagination, SocketRetryPolicy } from "./conversationRuntime";
const message = (id: number, expires_at: string | null = null): Message => ({
  id,
  conversation_id: 1,
  sender_id: 2,
  body: `消息${id}`,
  created_at: "2026-11-11T08:00:00Z",
  expires_at,
});

describe("history pagination survives displayed-message expiry", () => {
  it("can reach older permanent history after the entire latest page expires", async () => {
    const pages = new HistoryPagination();
    const latest = Array.from({ length: 50 }, (_, index) =>
      message(index + 2, "2026-11-11T09:00:00Z"),
    );
    pages.resetPage(latest);
    let visible = mergeMessages(latest, [], Date.parse("2026-11-11T10:00:00Z"));
    expect(visible).toEqual([]);
    const request = pages.beginOlder();
    expect(request?.before).toBe(2);
    const earlier = await Promise.resolve([message(1)]);
    if (request && pages.appendPage(earlier, request))
      visible = mergeMessages(visible, earlier);
    expect(visible.map((item) => item.id)).toEqual([1]);
    expect(pages.hasMore).toBe(false);
  });
  it("clears the prior context cursor and rejects its in-flight page after a conversation switch", () => {
    const pages = new HistoryPagination();
    pages.resetPage(
      Array.from({ length: 50 }, (_, index) => message(index + 51)),
    );
    const oldContextRequest = pages.beginOlder()!;
    pages.resetPage([]);
    expect(pages.beginOlder()).toBeNull();
    expect(pages.appendPage([message(1)], oldContextRequest)).toBe(false);
    expect(pages.hasMore).toBe(false);
  });
  it("resets the cursor on authoritative reconnect history and rejects an older in-flight page", () => {
    const pages = new HistoryPagination();
    pages.resetPage(
      Array.from({ length: 50 }, (_, index) => message(index + 51)),
    );
    const staleRequest = pages.beginOlder()!;
    pages.resetPage(
      Array.from({ length: 50 }, (_, index) => message(index + 151)),
    );
    expect(pages.appendPage([message(1)], staleRequest)).toBe(false);
    expect(pages.beginOlder()?.before).toBe(151);
  });
});

describe("WebSocket service recovery budget", () => {
  it("backs off and stops after five retries even when each transport opens before database rejection", () => {
    const retries = new SocketRetryPolicy();
    const delays: Array<number | null> = [];
    for (let attempt = 0; attempt < 6; attempt++) {
      const session = retries.startSession();
      // The handshake opened, but the server then rejected database validation.
      retries.rejectSession(session);
      retries.markHealthy(session); // A late HTTP result cannot rehabilitate this rejected socket.
      delays.push(retries.nextDelay(session, 1013));
    }
    expect(delays).toEqual([500, 1000, 2000, 4000, 8000, null]);
  });
  it("never retries a policy rejection, and a healthy current session restores the transient-failure budget", () => {
    const retries = new SocketRetryPolicy();
    const first = retries.startSession();
    expect(retries.nextDelay(first, 1013)).toBe(500);
    const second = retries.startSession();
    retries.markHealthy(first); // A stale socket's history response does not reset the budget.
    expect(retries.nextDelay(second, 1013)).toBe(1000);
    const healthy = retries.startSession();
    retries.markHealthy(healthy);
    expect(retries.nextDelay(healthy, 1006)).toBe(500);
    expect(retries.nextDelay(retries.startSession(), 1008)).toBeNull();
  });
});
