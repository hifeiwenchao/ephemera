import { describe, expect, it } from "vitest";
import { ConversationActivityGuard } from "./conversationState";
import type { Conversation } from "./types";
const conversation = (id: number): Conversation => ({
  id,
  other_user: {
    id: id + 1,
    username: `user${id}`,
    display_name: `用户${id}`,
    avatar_url: null,
  },
  ttl_seconds: null,
  created_at: "2026-11-11T08:00:00Z",
  updated_at: "2026-11-11T08:00:00Z",
  last_message: null,
  unread_count: 0,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("conversation HTTP/live activity ordering", () => {
  it("keeps a live TTL, preview and conversation order when an older list request resolves later", async () => {
    const guard = new ConversationActivityGuard();
    const first = conversation(1);
    const second = conversation(2);
    let state = [first, second];
    const response = deferred<Conversation[]>();
    const revision = guard.beginRequest();
    const refresh = response.promise.then((snapshot) => {
      state = guard.applySnapshot(state, snapshot, revision);
    });
    guard.recordActivity();
    state = [
      {
        ...second,
        ttl_seconds: 3600,
        updated_at: "2026-11-11T09:00:00Z",
        last_message: {
          id: 10,
          conversation_id: 2,
          sender_id: 3,
          body: "刚刚收到的新消息",
          created_at: "2026-11-11T09:00:00Z",
          expires_at: null,
        },
      },
      first,
    ];
    response.resolve([first, second]);
    await refresh;
    expect(state.map((item) => item.id)).toEqual([2, 1]);
    expect(state[0].ttl_seconds).toBe(3600);
    expect(state[0].last_message?.body).toBe("刚刚收到的新消息");
  });
  it("preserves live state when an idempotent create request returns an older matching conversation", async () => {
    const guard = new ConversationActivityGuard();
    const original = conversation(1);
    let state = [original];
    const response = deferred<Conversation>();
    const revision = guard.beginRequest();
    const create = response.promise.then((item) => {
      state = guard.applyConversationResponse(state, item, revision);
    });
    guard.recordActivity();
    state = [{ ...original, ttl_seconds: 604800 }];
    response.resolve(original);
    await create;
    expect(state[0].ttl_seconds).toBe(604800);
  });
  it("accepts a fresh list and retains a newly created conversation even if another conversation had live activity", () => {
    const guard = new ConversationActivityGuard();
    const first = conversation(1);
    const second = conversation(2);
    const revision = guard.beginRequest();
    expect(guard.applySnapshot([first], [second, first], revision)).toEqual([
      second,
      first,
    ]);
    guard.recordActivity();
    expect(
      guard
        .applyConversationResponse([first], second, revision)
        .map((item) => item.id),
    ).toEqual([first.id, second.id]);
  });
});
