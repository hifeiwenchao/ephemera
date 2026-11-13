import { afterEach, describe, expect, it, vi } from "vitest";
import * as runtime from "./conversationRuntime";
import type { Conversation } from "../types";
class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 0;
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: (event: { code: number }) => void;
  onerror?: () => void;
  constructor(public url: string) { Socket.instances.push(this); }
  open() { this.readyState = 1; this.onopen?.(); }
  message(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
  close(code = 1000) { this.readyState = 3; this.onclose?.({ code }); }
}
const conversation = (id: number): Conversation => ({
  id, other_user: { id: id + 1, username: `user${id}`, display_name: `用户${id}`, avatar_url: null },
  ttl_seconds: null, created_at: "2026-11-11T08:00:00Z", updated_at: "2026-11-11T08:00:00Z", last_message: null, unread_count: 2,
  other_last_read_message_id: null,
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); Socket.instances = []; });
function setup(resync: () => Promise<void> = async () => {}) {
  expect(runtime).toHaveProperty("subscribeConversationEvents");
  vi.stubGlobal("WebSocket", Socket);
  vi.useFakeTimers();
  const received: Conversation[] = [];
  const subscription = runtime.subscribeConversationEvents("ws://localhost/ws/events", (item: Conversation) => received.push(item), resync);
  return { subscription, received };
}
describe("global conversation events", () => {
  it("delivers unread updates for unopened and newly created conversations", () => {
    const { subscription, received } = setup();
    const socket = Socket.instances[0];
    expect(socket.url).toBe("ws://localhost/ws/events");
    socket.open();
    socket.message({ type: "conversation.updated", data: conversation(8) });
    socket.message({ type: "conversation.updated", data: conversation(42) });
    expect(received.map((item) => [item.id, item.unread_count])).toEqual([[8, 2], [42, 2]]);
    subscription.close();
  });
  it("resyncs the full list on open and after reconnect", async () => {
    let syncs = 0;
    const { subscription } = setup(async () => { syncs++; });
    Socket.instances[0].open();
    await Promise.resolve();
    expect(syncs).toBe(1);
    Socket.instances[0].close(1006);
    await vi.advanceTimersByTimeAsync(500);
    Socket.instances[1].open();
    await Promise.resolve();
    expect(syncs).toBe(2);
    subscription.close();
  });
  it("stops socket callbacks and scheduled retries after logout or identity change", async () => {
    const { subscription, received } = setup();
    const socket = Socket.instances[0];
    socket.close(1006);
    subscription.close();
    socket.message({ type: "conversation.updated", data: conversation(8) });
    await vi.advanceTimersByTimeAsync(1000);
    expect(Socket.instances).toHaveLength(1);
    expect(received).toEqual([]);
  });
});
