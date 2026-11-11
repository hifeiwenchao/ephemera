import { useEffect, useRef, useState } from "react";
import { Clock3, LoaderCircle, Send } from "lucide-react";
import type { TtlSeconds } from "../types";
import { ttlLabel } from "../display";
export default function MessageComposer({
  draftKey,
  connected,
  ttl,
  onSend,
}: {
  draftKey: string;
  connected: boolean;
  ttl: TtlSeconds;
  onSend: (body: string) => Promise<void>;
}) {
  const [text, setText] = useState(
    () => sessionStorage.getItem(draftKey) || "",
  );
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    sessionStorage.setItem(draftKey, text);
    const element = textarea.current;
    if (element) {
      element.style.height = "30px";
      element.style.height = `${Math.min(140, element.scrollHeight)}px`;
    }
  }, [draftKey, text]);
  async function send() {
    const body = text.trim();
    if (!body || sending || !connected) return;
    setSending(true);
    setError("");
    try {
      await onSend(body);
      setText("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "发送失败，输入内容已保留",
      );
    } finally {
      setSending(false);
      requestAnimationFrame(() => textarea.current?.focus());
    }
  }
  return (
    <div className="chat-bottom">
      <div className="ttl-notice">
        <Clock3 size={11} />
        {ttl ? (
          <>
            新消息将在 <strong>{ttlLabel(ttl)}</strong> 后自动删除
          </>
        ) : (
          <>一来一往，让心意慢慢抵达</>
        )}
      </div>
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <textarea
          ref={textarea}
          value={text}
          disabled={sending}
          maxLength={4000}
          rows={1}
          aria-label="输入消息"
          placeholder={
            connected
              ? "写点什么，让对话继续…"
              : "连接恢复后即可发送，草稿会为你保留…"
          }
          onChange={(event) => {
            setText(event.target.value);
            setError("");
          }}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="composer-tools">
          <span className="composer-hint">
            {text.length > 3500 ? `${text.length} / 4000` : "Enter 发送"}
          </span>
          <button
            type="submit"
            className="send-button"
            disabled={!text.trim() || !connected || sending}
            aria-label={sending ? "正在发送" : "发送消息"}
            title="发送消息"
          >
            {sending ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <Send size={17} strokeWidth={1.7} />
            )}
          </button>
        </div>
      </form>
      {error && (
        <div className="composer-error" role="alert">
          {error}
        </div>
      )}
      <p className="composer-footnote">
        Shift + Enter 换行 · 简单一点，聊得自在
      </p>
    </div>
  );
}
