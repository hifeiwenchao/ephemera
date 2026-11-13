import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import MessageList from "./MessageList";
import type { Message, User } from "../types";
const me: User = { id: 1, username: "alice", display_name: "艾莉丝", avatar_url: null };
const peer: User = { id: 2, username: "bob", display_name: "林间", avatar_url: null };
const message = (id: number, sender_id = me.id): Message => ({
  id, sender_id, conversation_id: 7, body: `消息${id}`,
  created_at: "2026-11-11T08:00:00Z", expires_at: null,
});
function render(messages: Message[], cursor: number | null) {
  return renderToStaticMarkup(<MessageList messages={messages} currentUser={me} otherUser={peer}
    loading={false} hasMore={false} loadingOlder={false} onLoadOlder={async () => {}}
    conversationId={7} historyLoaded onMessagesRendered={() => {}} otherLastReadMessageId={cursor} />);
}
describe("outgoing message read receipts", () => {
  it("shows one sent check when the peer has no read cursor", () => {
    const markup = render([message(10)], null);
    expect(markup).toContain('aria-label="已发送"');
    expect(markup).toContain('title="已发送，未读"');
    expect(markup).not.toContain("lucide-check-check");
  });
  it.each([
    [9, "已发送"], [10, "对方已读"], [11, "对方已读"],
  ] as const)("shows the correct receipt for message10 and peer boundary%s", (cursor, label) => {
    const markup = render([message(10)], cursor);
    expect(markup).toContain(`aria-label="${label}"`);
    if (label === "对方已读") {
      expect(markup).toContain("lucide-check-check");
      expect(markup).toContain('title="对方已读"');
      expect(markup).toContain("is-read");
    } else expect(markup).not.toContain("lucide-check-check");
  });
  it("uses each outgoing message ID in a mixed incoming and outgoing history", () => {
    const rows = render([message(5), message(6, peer.id), message(7), message(8)], 7)
      .match(/<article[\s\S]*?<\/article>/g)!;
    expect(rows[0]).toContain('aria-label="对方已读"');
    expect(rows[1]).not.toContain("message-status");
    expect(rows[2]).toContain('aria-label="对方已读"');
    expect(rows[3]).toContain('aria-label="已发送"');
  });
  it("does not add own-message receipts to incoming messages", () => {
    expect(render([message(5, peer.id)], 100)).not.toContain("message-status");
    expect(render([message(5, peer.id)], 100)).not.toContain('aria-label="已发送"');
  });
  it("does not render a status without messages", () => {
    expect(render([], 100)).not.toContain("message-status");
  });
});
