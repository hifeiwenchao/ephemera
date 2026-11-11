import { useCallback, useEffect, useRef, useState } from "react";
import { listMessages, socketUrl } from "../api";
import { applyMessageEvent, mergeMessages } from "../messages";
import { HistoryPagination, SocketRetryPolicy } from "./conversationRuntime";
import type { Conversation, Message, SocketEvent } from "../types";
export type ConnectionState =
  "connecting" | "connected" | "reconnecting" | "disconnected";
type Pending = {
  body: string;
  resolve: () => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};
export function useConversation(
  userId: number | null,
  conversationId: number | null,
  onActivity: (conversation: Partial<Conversation> & { id: number }) => void,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [error, setError] = useState("");
  const [generation, setGeneration] = useState(0);
  const socket = useRef<WebSocket | null>(null);
  const pending = useRef<Pending | null>(null);
  const activity = useRef(onActivity);
  activity.current = onActivity;
  const pagination = useRef(new HistoryPagination());
  const activeContext = useRef("");
  activeContext.current = `${userId}:${conversationId}:${generation}`;
  useEffect(() => {
    setMessages([]);
    setHasMore(false);
    setError("");
    pagination.current.resetPage([]);
    if (!userId || !conversationId) return;
    let disposed = false;
    const retries = new SocketRetryPolicy();
    let reconnectTimer: ReturnType<typeof setTimeout>;
    const tombstones = new Set<number>();
    const receivedEvents: Message[] = [];
    let syncRevision = 0;
    setLoadingOlder(false);
    setLoading(true);
    setConnection("connecting");
    const rejectPending = (message: string) => {
      if (pending.current) {
        clearTimeout(pending.current.timer);
        pending.current.reject(new Error(message));
        pending.current = null;
      }
    };
    const sync = async (connectedSocket?: WebSocket, session?: number) => {
      const revision = ++syncRevision;
      const eventIndex = receivedEvents.length;
      try {
        const history = await listMessages(userId, conversationId);
        if (!disposed && revision === syncRevision) {
          setMessages(() =>
            mergeMessages(history, receivedEvents.slice(eventIndex)).filter(
              (message) => !tombstones.has(message.id),
            ),
          );
          pagination.current.resetPage(history);
          setHasMore(pagination.current.hasMore);
          if (
            connectedSocket &&
            session !== undefined &&
            socket.current === connectedSocket &&
            connectedSocket.readyState === WebSocket.OPEN
          )
            retries.markHealthy(session);
          setError("");
        }
      } catch (cause) {
        if (!disposed)
          setError(cause instanceof Error ? cause.message : "历史消息加载失败");
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    void sync();
    const connect = () => {
      if (disposed) return;
      const session = retries.startSession();
      const ws = new WebSocket(socketUrl(userId, conversationId));
      socket.current = ws;
      ws.onopen = () => {
        if (disposed || socket.current !== ws) return;
        setConnection("connected");
        void sync(ws, session);
      };
      ws.onmessage = (event) => {
        if (disposed || socket.current !== ws) return;
        let payload: SocketEvent;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        if (payload.type === "message.created") {
          const message = payload.data as Message;
          receivedEvents.push(message);
          setMessages((previous) => applyMessageEvent(previous, payload));
          activity.current({
            id: conversationId,
            last_message: message,
            updated_at: message.created_at,
          });
          if (
            pending.current &&
            message.sender_id === userId &&
            message.body === pending.current.body
          ) {
            clearTimeout(pending.current.timer);
            pending.current.resolve();
            pending.current = null;
          }
        } else if (payload.type === "message.deleted") {
          for (const id of (payload.data as { ids: number[] }).ids)
            tombstones.add(id);
          setMessages((previous) => applyMessageEvent(previous, payload));
        } else if (payload.type === "conversation.updated")
          activity.current(
            payload.data as Partial<Conversation> & { id: number },
          );
        else if (payload.type === "error") {
          if (payload.code === "database_unavailable")
            retries.rejectSession(session);
          const message = payload.message || "消息发送失败，请稍后重试";
          setError(message);
          rejectPending(message);
        }
      };
      ws.onclose = (event) => {
        if (disposed || socket.current !== ws) return;
        rejectPending("连接已断开，输入内容已保留");
        const delay = retries.nextDelay(session, event.code);
        if (delay !== null) {
          setConnection("reconnecting");
          reconnectTimer = setTimeout(connect, delay);
        } else setConnection("disconnected");
      };
      ws.onerror = () => {
        /* onclose owns retries and visible connection state. */
      };
    };
    connect();
    const expirationTimer = setInterval(
      () =>
        setMessages((previous) =>
          previous.some(
            (message) =>
              message.expires_at &&
              Date.parse(message.expires_at) <= Date.now(),
          )
            ? mergeMessages(previous, [])
            : previous,
        ),
      1000,
    );
    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      clearInterval(expirationTimer);
      rejectPending("会话已切换，输入内容已保留");
      const ws = socket.current;
      socket.current = null;
      ws?.close();
    };
  }, [userId, conversationId, generation]);
  const send = useCallback((body: string): Promise<void> => {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN)
      return Promise.reject(new Error("尚未连接，输入内容已保留"));
    if (pending.current) return Promise.reject(new Error("上一条消息正在发送"));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.current = null;
        reject(new Error("尚未收到服务端确认，请检查连接后重试"));
      }, 12000);
      pending.current = { body, resolve, reject, timer };
      try {
        ws.send(JSON.stringify({ type: "message.send", body }));
      } catch {
        clearTimeout(timer);
        pending.current = null;
        reject(new Error("发送失败，输入内容已保留"));
      }
    });
  }, []);
  const loadOlder = useCallback(async () => {
    if (!userId || !conversationId || loadingOlder) return;
    const pageState = pagination.current;
    const request = pageState.beginOlder();
    if (!request) return;
    const context = activeContext.current;
    setLoadingOlder(true);
    try {
      const older = await listMessages(userId, conversationId, request.before);
      if (
        context === activeContext.current &&
        pagination.current === pageState &&
        pageState.appendPage(older, request)
      ) {
        setMessages((previous) => mergeMessages(previous, older));
        setHasMore(pageState.hasMore);
      }
    } catch (cause) {
      if (context === activeContext.current)
        setError(cause instanceof Error ? cause.message : "加载失败");
    } finally {
      if (context === activeContext.current) setLoadingOlder(false);
    }
  }, [userId, conversationId, loadingOlder]);
  return {
    messages,
    loading,
    loadingOlder,
    hasMore,
    connection,
    error,
    send,
    loadOlder,
    reconnect: () => setGeneration((value) => value + 1),
    clearError: () => setError(""),
  };
}
