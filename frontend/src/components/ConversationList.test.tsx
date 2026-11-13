import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ConversationList from "./ConversationList";
import type { Conversation } from "../types";
const conversation: Conversation = {
  id: 1,
  other_user: { id: 2, username: "bob", display_name: "林间", avatar_url: null },
  ttl_seconds: null,
  created_at: "2026-11-11T08:00:00Z",
  updated_at: "2026-11-11T08:00:00Z",
  last_message: null,
  unread_count: 3,
  other_last_read_message_id: null,
};
function render(unread: number) {
  return renderToStaticMarkup(<ConversationList conversations={[{ ...conversation, unread_count: unread }]} selectedId={null} userId={1} loading={false} onSelect={() => {}} />);
}
describe("conversation unread badge", () => {
  it("shows the unread number with an accessible label", () => {
    expect(render(3)).toContain('aria-label="3 条未读消息"');
    expect(render(3)).toMatch(/class="unread-badge"[^>]*>3<\/span>/);
  });
  it("caps the visible number while keeping the exact accessible count", () => {
    expect(render(103)).toContain('aria-label="103 条未读消息"');
    expect(render(103)).toContain(">99+</span>");
  });
  it("does not show a badge after all messages have been read", () => {
    expect(render(0)).not.toContain("unread-badge");
  });
});

describe("conversation preview read receipts", () => {
  function preview(senderId: number, cursor: number | null) {
    return renderToStaticMarkup(<ConversationList conversations={[{
      ...conversation,
      other_last_read_message_id: cursor,
      last_message: { id: 10, conversation_id: 1, sender_id: senderId, body: "最新消息", created_at: conversation.updated_at, expires_at: null },
    }]} selectedId={null} userId={1} loading={false} onSelect={() => {}} />);
  }
  it("shows the same sent state for an unread outgoing preview", () => {
    expect(preview(1, 9)).toContain('aria-label="已发送"');
    expect(preview(1, 9)).toContain('title="已发送，未读"');
    expect(preview(1, 9)).not.toContain("lucide-check-check");
  });
  it("shows the same read state when the peer reached the preview message", () => {
    expect(preview(1, 10)).toContain('aria-label="对方已读"');
    expect(preview(1, 10)).toContain("lucide-check-check");
  });
  it("does not show a receipt for an incoming preview", () => {
    expect(preview(2, 100)).not.toContain("message-status");
    expect(preview(2, 100)).not.toContain('aria-label="对方已读"');
  });
});
