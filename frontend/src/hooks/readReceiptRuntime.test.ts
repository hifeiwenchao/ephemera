import { describe, expect, it } from "vitest";
import * as runtime from "./conversationRuntime";
function deferred() {
  let resolve!: () => void;
  let reject!: () => void;
  const promise = new Promise<void>((done, fail) => { resolve = done; reject = () => fail(new Error("offline")); });
  return { promise, resolve, reject };
}
async function settle() { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); }
function setup() {
  expect(runtime).toHaveProperty("ReadReceiptScheduler");
  const sent: Array<[number, number, number]> = [];
  const pending: ReturnType<typeof deferred>[] = [];
  const scheduler = new runtime.ReadReceiptScheduler((userId: number, conversationId: number, messageId: number) => {
    sent.push([userId, conversationId, messageId]);
    const response = deferred(); pending.push(response); return response.promise;
  });
  scheduler.setContext(1, 10);
  scheduler.setAttention(true);
  return { scheduler, sent, pending };
}
describe("read receipts only acknowledge rendered messages", () => {
  it("does not mark a selected conversation until its incoming messages were rendered", () => {
    const { scheduler, sent } = setup();
    scheduler.retry();
    expect(sent).toEqual([]);
    scheduler.rendered(1, 10, 42);
    expect(sent).toEqual([[1, 10, 42]]);
  });
  it("keeps hidden or unfocused messages unread until attention returns", () => {
    const { scheduler, sent } = setup();
    scheduler.setAttention(false);
    scheduler.rendered(1, 10, 42);
    scheduler.retry();
    expect(sent).toEqual([]);
    scheduler.setAttention(true);
    expect(sent).toEqual([[1, 10, 42]]);
  });
  it("ignores a previous conversation or user's render after switching", () => {
    const { scheduler, sent } = setup();
    scheduler.setContext(2, 20);
    scheduler.rendered(1, 10, 42);
    scheduler.rendered(1, 20, 43);
    scheduler.retry();
    expect(sent).toEqual([]);
    scheduler.rendered(2, 20, 44);
    expect(sent).toEqual([[2, 20, 44]]);
  });
  it("retries failures on resync and does not resend an acknowledged boundary", async () => {
    const { scheduler, sent, pending } = setup();
    scheduler.rendered(1, 10, 42);
    pending[0].reject(); await settle();
    expect(sent).toHaveLength(1);
    scheduler.retry();
    expect(sent).toHaveLength(2);
    pending[1].resolve(); await settle();
    scheduler.rendered(1, 10, 42); scheduler.retry();
    expect(sent).toHaveLength(2);
  });
  it("acknowledges a newer rendered incoming message after the prior request completes", async () => {
    const { scheduler, sent, pending } = setup();
    scheduler.rendered(1, 10, 42);
    scheduler.rendered(1, 10, 43);
    pending[0].resolve(); await settle();
    expect(sent).toEqual([[1, 10, 42], [1, 10, 43]]);
  });
  it("does not reuse the previous conversation's boundary while its request is in flight", async () => {
    const { scheduler, sent, pending } = setup();
    scheduler.rendered(1, 10, 42);
    scheduler.setContext(1, 20);
    pending[0].resolve(); await settle();
    scheduler.retry();
    expect(sent).toEqual([[1, 10, 42]]);
    scheduler.rendered(1, 20, 9);
    expect(sent).toEqual([[1, 10, 42], [1, 20, 9]]);
  });
});

describe("rendered incoming read boundary", () => {
  const incoming = { id: 42, conversation_id: 10, sender_id: 2, body: "收到", created_at: "2026-11-11T08:00:00Z", expires_at: null };
  it("waits for history to load and rejects another conversation's message array", () => {
    expect(runtime).toHaveProperty("renderedIncomingBoundary");
    expect(runtime.renderedIncomingBoundary([incoming], 1, 10, false)).toBeNull();
    expect(runtime.renderedIncomingBoundary([incoming], 1, 20, true)).toBeNull();
    expect(runtime.renderedIncomingBoundary([incoming], 1, 10, true)).toBe(42);
  });
  it("uses the last received ID instead of a newer outgoing message", () => {
    expect(runtime).toHaveProperty("renderedIncomingBoundary");
    expect(runtime.renderedIncomingBoundary([incoming, { ...incoming, id: 50, sender_id: 1 }], 1, 10, true)).toBe(42);
    expect(runtime.renderedIncomingBoundary([{ ...incoming, sender_id: 1 }], 1, 10, true)).toBeNull();
  });
});

describe("current conversation message ownership", () => {
  const incoming = { id: 42, conversation_id: 10, sender_id: 2, body: "实时收到", created_at: "2026-11-11T08:00:00Z", expires_at: null };
  it("shows a live message after failed history without allowing a read receipt", () => {
    expect(runtime).toHaveProperty("conversationView");
    const view = runtime.conversationView([incoming], "1:10:0", "", "1:10:0");
    expect(view.messages).toEqual([incoming]);
    expect(view.historyLoaded).toBe(false);
    expect(runtime.renderedIncomingBoundary(view.messages, 1, 10, view.historyLoaded)).toBeNull();
  });
  it("hides a previous conversation or user's messages immediately on a view switch", () => {
    expect(runtime).toHaveProperty("conversationView");
    expect(runtime.conversationView([incoming], "1:10:0", "1:10:0", "1:20:0").messages).toEqual([]);
    expect(runtime.conversationView([incoming], "1:10:0", "1:10:0", "2:10:0").messages).toEqual([]);
  });
});
