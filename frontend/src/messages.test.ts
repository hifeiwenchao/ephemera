import { describe, expect, it } from "vitest";
import { mergeMessages, applyMessageEvent } from "./messages";
import type { Message } from "./types";
const message = (id: number, overrides: Partial<Message> = {}): Message => ({
  id,
  conversation_id: 1,
  sender_id: 2,
  body: `消息 ${id}`,
  created_at: `2026-11-11T10:00:0${id}Z`,
  expires_at: null,
  ...overrides,
});
describe("live history reconciliation", () => {
  it("deduplicates a live event already present in fetched history and preserves chronological order", () => {
    expect(
      mergeMessages([message(2)], [message(1), message(2)], 0).map((m) => m.id),
    ).toEqual([1, 2]);
  });
  it("removes expired messages even before the cleanup broadcast arrives", () => {
    const now = Date.parse("2026-11-11T11:00:00Z");
    expect(
      mergeMessages(
        [message(1, { expires_at: "2026-11-11T10:59:00Z" })],
        [message(2)],
        now,
      ).map((m) => m.id),
    ).toEqual([2]);
  });
  it("applies deletion broadcasts and ignores unknown events", () => {
    const result = applyMessageEvent(
      [message(1), message(2)],
      { type: "message.deleted", data: { ids: [1] } },
      0,
    );
    expect(result.map((m) => m.id)).toEqual([2]);
    expect(applyMessageEvent(result, { type: "unknown" }, 0)).toEqual(result);
  });
});
