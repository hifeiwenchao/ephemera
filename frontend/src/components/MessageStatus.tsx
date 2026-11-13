import { Check, CheckCheck } from "lucide-react";

export default function MessageStatus({
  messageId,
  otherLastReadMessageId,
  className = "",
}: {
  messageId: number;
  otherLastReadMessageId: number | null;
  className?: string;
}) {
  const read = otherLastReadMessageId !== null && messageId <= otherLastReadMessageId;
  const Icon = read ? CheckCheck : Check;
  return (
    <span
      className={`message-status ${className}${read ? " is-read" : ""}`}
      role="img"
      aria-label={read ? "对方已读" : "已发送"}
      title={read ? "对方已读" : "已发送，未读"}
    >
      <Icon size={13} aria-hidden="true" />
    </span>
  );
}
