import { ArrowLeft, Info } from "lucide-react";
import type { Conversation, TtlSeconds } from "../types";
import type { ConnectionState } from "../hooks/useConversation";
import Avatar from "./Avatar";
import TtlPopover from "./TtlPopover";
export default function ChatHeader({
  conversation,
  connection,
  onBack,
  onTtlChange,
  onInfo,
}: {
  conversation: Conversation;
  connection: ConnectionState;
  onBack: () => void;
  onTtlChange: (ttl: TtlSeconds) => Promise<void>;
  onInfo: () => void;
}) {
  const online = connection === "connected";
  return (
    <header className="chat-header">
      <button
        className="back-button"
        aria-label="返回消息列表"
        onClick={onBack}
      >
        <ArrowLeft size={21} />
      </button>
      <Avatar user={conversation.other_user} />
      <div className="chat-heading">
        <h2>{conversation.other_user.display_name}</h2>
        <div className={`chat-status ${online ? "" : "offline"}`}>
          <span className="connection-dot" />
          {online
            ? "实时连接已建立"
            : connection === "connecting"
              ? "正在连接…"
              : connection === "reconnecting"
                ? "连接中断 · 正在重连"
                : "已断开连接"}
          <span>·</span>
          <span>@{conversation.other_user.username}</span>
        </div>
      </div>
      <div className="header-actions">
        <TtlPopover value={conversation.ttl_seconds} onChange={onTtlChange} />
        <div className="header-separator" />
        <button
          className="icon-button"
          aria-label="查看会话资料"
          title="会话资料"
          onClick={onInfo}
        >
          <Info size={19} strokeWidth={1.5} />
        </button>
      </div>
    </header>
  );
}
