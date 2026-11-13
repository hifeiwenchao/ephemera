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
  other_last_read_message_id: null,
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
    const revision = guard.beginSnapshot();
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
    expect(guard.applySnapshot([first], [second, first], guard.beginSnapshot())).toEqual([
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

describe("unread response ordering", () => {
  it("does not clear a newly arrived unread message when an older read response resolves", () => {
    const guard = new ConversationActivityGuard();
    const original = { ...conversation(1), unread_count: 1 };
    const revision = guard.beginRequest();
    guard.recordActivity();
    const latest = { ...original, unread_count: 2 };
    expect(guard.applyConversationResponse([latest], { ...original, unread_count: 0 }, revision)[0].unread_count).toBe(2);
  });
  it("upserts an unopened conversation or a brand new conversation event", () => {
    const guard = new ConversationActivityGuard();
    const existing = conversation(1);
    const update = { ...conversation(2), unread_count: 3 };
    let state = guard.applyConversationResponse([existing], update, guard.beginRequest());
    state = guard.applyConversationResponse(state, { ...update, unread_count: 4 }, guard.beginRequest());
    expect(state.find((item) => item.id === 2)?.unread_count).toBe(4);
    expect(state).toHaveLength(2);
  });
});

describe("initial snapshot racing with unread events", () => {
  it("adds missing initial conversations without reverting a live unread count", () => {
    const guard = new ConversationActivityGuard();
    const revision = guard.beginSnapshot();
    const first = conversation(1);
    const second = conversation(2);
    const third = conversation(3);
    guard.recordActivity();
    const liveSecond = { ...second, unread_count: 2, updated_at: "2026-11-11T09:00:00Z" };
    const state = guard.applySnapshot([liveSecond], [first, second, third], revision);
    expect(state.map((item) => item.id)).toEqual([2, 1, 3]);
    expect(state.find((item) => item.id === 2)?.unread_count).toBe(2);
  });
});

describe("overlapping HTTP response ordering", () => {
  it("keeps the newer reconnect snapshot when the initial list resolves afterward", () => {
    const guard = new ConversationActivityGuard();
    const first = conversation(1);
    const missed = conversation(2);
    const initial = guard.beginSnapshot();
    const reconnect = guard.beginSnapshot();
    let state = guard.applySnapshot([], [{ ...first, unread_count: 1 }], reconnect);
    state = guard.applySnapshot(state, [first, missed], initial);
    expect(state.find((item) => item.id === 1)?.unread_count).toBe(1);
    expect(state.map((item) => item.id)).toEqual([1, 2]);
  });
  it("rejects an old read response after a newer list snapshot has applied", () => {
    const guard = new ConversationActivityGuard();
    const first = conversation(1);
    const readRevision = guard.beginRequest();
    const snapshotRevision = guard.beginSnapshot();
    const state = guard.applySnapshot([first], [{ ...first, unread_count: 1 }], snapshotRevision);
    expect(guard.applyConversationResponse(state, first, readRevision)[0].unread_count).toBe(1);
  });
  it("accepts a newer list issued at the same activity revision", () => {
    const guard = new ConversationActivityGuard();
    const first = conversation(1);
    const initial = guard.beginSnapshot();
    const reconnect = guard.beginSnapshot();
    const state = guard.applySnapshot([], [first], initial);
    expect(guard.applySnapshot(state, [{ ...first, unread_count: 1 }], reconnect)[0].unread_count).toBe(1);
  });
  it("reapplies the same snapshot without invalidating later HTTP requests", () => {
    const guard = new ConversationActivityGuard();
    const first = conversation(1);
    const request = guard.beginSnapshot();
    const state = guard.applySnapshot([], [first], request);
    const responseRevision = guard.beginRequest();
    expect(guard.applySnapshot(state, [first], request)).toEqual([first]);
    expect(guard.beginRequest()).toBe(responseRevision);
  });
});

describe("peer read cursor response ordering", () => {
  it("preserves a live peer read cursor when an older list finishes", () => {
    const guard = new ConversationActivityGuard();
    const request = guard.beginSnapshot();
    const old = { ...conversation(1), other_last_read_message_id: 5 };
    guard.recordActivity();
    const live = { ...old, other_last_read_message_id: 10 };
    expect(guard.applySnapshot([live], [old], request)[0].other_last_read_message_id).toBe(10);
  });
  it("preserves the newer HTTP peer cursor when an overlapping old snapshot finishes", () => {
    const guard = new ConversationActivityGuard();
    const older = guard.beginSnapshot();
    const newer = guard.beginSnapshot();
    const old = { ...conversation(1), other_last_read_message_id: 5 };
    const state = guard.applySnapshot([], [{ ...old, other_last_read_message_id: 10 }], newer);
    expect(guard.applySnapshot(state, [old], older)[0].other_last_read_message_id).toBe(10);
  });
});
