import { Fragment, useEffect, useRef } from "react";
import { Clock3, LoaderCircle } from "lucide-react";
import type { Message, User } from "../types";
import { dateLabel, expirationLabel, timeLabel } from "../display";
import Avatar from "./Avatar";
import MessageStatus from "./MessageStatus";
import { renderedIncomingBoundary } from "../hooks/conversationRuntime";
export default function MessageList({
  messages,
  currentUser,
  otherUser,
  loading,
  hasMore,
  loadingOlder,
  onLoadOlder,
  conversationId,
  historyLoaded,
  onMessagesRendered,
  otherLastReadMessageId,
}: {
  messages: Message[];
  currentUser: User;
  otherUser: User;
  loading: boolean;
  hasMore: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => Promise<void>;
  conversationId: number;
  historyLoaded: boolean;
  onMessagesRendered: (messageId: number | null) => void;
  otherLastReadMessageId: number | null;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const initial = useRef(true);
  const lastId = messages[messages.length - 1]?.id;
  useEffect(() => {
    if (!loading && historyLoaded)
      onMessagesRendered(renderedIncomingBoundary(messages, currentUser.id, conversationId, historyLoaded));
  }, [messages, currentUser.id, conversationId, loading, historyLoaded, onMessagesRendered]);
  useEffect(() => {
    const element = scroller.current;
    if (element && (initial.current || nearBottom.current)) {
      element.scrollTop = element.scrollHeight;
      if (!loading) initial.current = false;
    }
  }, [lastId, loading]);
  async function older() {
    const element = scroller.current;
    const height = element?.scrollHeight || 0;
    const top = element?.scrollTop || 0;
    nearBottom.current = false;
    await onLoadOlder();
    requestAnimationFrame(() => {
      if (element) element.scrollTop = top + element.scrollHeight - height;
    });
  }
  return (
    <div
      className="message-area chat-pattern"
      ref={scroller}
      role="log"
      aria-label="聊天记录"
      aria-live="polite"
      onScroll={() => {
        const element = scroller.current;
        if (element)
          nearBottom.current =
            element.scrollHeight - element.scrollTop - element.clientHeight <
            120;
      }}
    >
      <div className="messages-container">
        {loading && !messages.length ? (
          <div className="message-loading">
            <LoaderCircle size={17} className="spin" />
            正在打开对话…
          </div>
        ) : (
          <>
            {hasMore ? (
              <button
                className="history-button"
                disabled={loadingOlder}
                onClick={() => void older()}
              >
                {loadingOlder ? "正在加载…" : "查看更早的消息"}
              </button>
            ) : (
              <div className="conversation-start">
                <Avatar user={otherUser} size="large" />
                <h3>你与{otherUser.display_name}的对话</h3>
                <p>每一段好对话，都值得被认真对待</p>
              </div>
            )}
            {messages.map((message, index) => {
              const outgoing = message.sender_id === currentUser.id;
              const day = new Date(message.created_at).toDateString();
              const showDate =
                !index ||
                new Date(messages[index - 1].created_at).toDateString() !== day;
              return (
                <Fragment key={message.id}>
                  {showDate && (
                    <div className="date-divider">
                      <span>{dateLabel(message.created_at)}</span>
                    </div>
                  )}
                  <article
                    className={`message-row ${outgoing ? "outgoing" : ""}`}
                    aria-label={`${outgoing ? "我" : otherUser.display_name}：${message.body}`}
                  >
                    <Avatar user={outgoing ? currentUser : otherUser} />
                    <div className="message-bubble">
                      <div className="message-body">{message.body}</div>
                      <div className="message-meta">
                        {message.expires_at && (
                          <span
                            className="expiration-badge"
                            title={`自动删除时间：${new Date(message.expires_at).toLocaleString("zh-CN")}`}
                          >
                            <Clock3 size={9} />
                            {expirationLabel(message.expires_at)}
                          </span>
                        )}
                        <time dateTime={message.created_at}>
                          {timeLabel(message.created_at)}
                        </time>
                        {outgoing && (
                          <MessageStatus
                            messageId={message.id}
                            otherLastReadMessageId={otherLastReadMessageId}
                            className="delivery"
                          />
                        )}
                      </div>
                    </div>
                  </article>
                </Fragment>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
