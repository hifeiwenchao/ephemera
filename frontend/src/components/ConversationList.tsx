import { Check, MessageCircle } from "lucide-react";
import type { Conversation } from "../types";
import { previewTime } from "../display";
import Avatar from "./Avatar";
export default function ConversationList({
  conversations,
  selectedId,
  userId,
  loading,
  onSelect,
}: {
  conversations: Conversation[];
  selectedId: number | null;
  userId: number | null;
  loading: boolean;
  onSelect: (id: number) => void;
}) {
  if (loading)
    return (
      <>
        {[1, 2, 3].map((id) => (
          <div className="skeleton" key={id}>
            <div className="loading-avatar" />
            <div className="lines">
              <div className="loading-line" />
              <div className="loading-line" />
            </div>
          </div>
        ))}
      </>
    );
  if (!conversations.length)
    return (
      <div className="sidebar-empty">
        <MessageCircle size={31} strokeWidth={1.2} />
        <strong>好对话，从一声问候开始</strong>搜索用户名，找到你想聊的人
      </div>
    );
  return (
    <>
      {conversations.map((conversation) => (
        <button
          className={`conversation-item ${selectedId === conversation.id ? "selected" : ""}`}
          aria-current={selectedId === conversation.id ? "true" : undefined}
          key={conversation.id}
          onClick={() => onSelect(conversation.id)}
        >
          <Avatar user={conversation.other_user} />
          <div className="conversation-details">
            <div className="conversation-line">
              <span className="conversation-name">
                {conversation.other_user.display_name}
              </span>
              <time className="conversation-time">
                {previewTime(
                  conversation.last_message?.created_at ||
                    conversation.updated_at,
                )}
              </time>
            </div>
            <p className="conversation-preview">
              {conversation.last_message?.sender_id === userId && (
                <Check size={13} className="preview-check" />
              )}
              {conversation.last_message?.body || "打个招呼，开始你们的对话"}
            </p>
          </div>
        </button>
      ))}
    </>
  );
}
