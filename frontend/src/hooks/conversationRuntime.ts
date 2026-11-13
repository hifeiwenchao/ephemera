import type { Conversation, Message, SocketEvent } from "../types";

type PageRequest = { before: number; revision: number };

/** The API page boundary survives removal of expired messages from the view. */
export class HistoryPagination {
  hasMore = false;
  private cursor: number | undefined;
  private revision = 0;

  resetPage(page: Message[]) {
    this.revision += 1;
    this.cursor = page[0]?.id;
    this.hasMore = page.length === 50;
  }

  beginOlder(): PageRequest | null {
    return this.hasMore && this.cursor !== undefined
      ? { before: this.cursor, revision: this.revision }
      : null;
  }

  appendPage(page: Message[], request: PageRequest): boolean {
    if (request.revision !== this.revision || request.before !== this.cursor)
      return false;
    this.cursor = page[0]?.id ?? this.cursor;
    this.hasMore = page.length === 50;
    return true;
  }
}

/** Transport handshakes do not establish that the authenticated service is healthy. */
export class SocketRetryPolicy {
  private session = 0;
  private rejectedSession: number | null = null;
  private attempts = 0;

  startSession(): number {
    return ++this.session;
  }

  rejectSession(session: number) {
    if (session === this.session) this.rejectedSession = session;
  }

  markHealthy(session: number) {
    if (session === this.session && session !== this.rejectedSession)
      this.attempts = 0;
  }

  nextDelay(session: number, closeCode: number): number | null {
    if (session !== this.session || closeCode === 1008 || this.attempts >= 5)
      return null;
    return 500 * 2 ** this.attempts++;
  }
}

/** A receipt can advance only to incoming messages committed in the active view. */
export class ReadReceiptScheduler {
  private userId: number | null = null;
  private conversationId: number | null = null;
  private renderedId: number | null = null;
  private attentive = false;
  private acknowledged = new Map<string, number>();
  private pending = new Set<string>();

  constructor(
    private send: (
      userId: number,
      conversationId: number,
      messageId: number,
    ) => Promise<void>,
  ) {}

  setContext(userId: number | null, conversationId: number | null) {
    if (userId !== this.userId || conversationId !== this.conversationId)
      this.renderedId = null;
    this.userId = userId;
    this.conversationId = conversationId;
  }

  setAttention(attentive: boolean) {
    this.attentive = attentive;
    this.retry();
  }

  rendered(userId: number, conversationId: number, messageId: number | null) {
    if (userId !== this.userId || conversationId !== this.conversationId) return;
    this.renderedId = messageId;
    this.retry();
  }

  retry() {
    if (!this.attentive || !this.userId || !this.conversationId || this.renderedId === null)
      return;
    const userId = this.userId;
    const conversationId = this.conversationId;
    const messageId = this.renderedId;
    const key = `${userId}:${conversationId}`;
    if (this.pending.has(key) || messageId <= (this.acknowledged.get(key) ?? 0))
      return;
    this.pending.add(key);
    void (async () => {
      let succeeded = false;
      try {
        await this.send(userId, conversationId, messageId);
        this.acknowledged.set(
          key, Math.max(messageId, this.acknowledged.get(key) ?? 0),
        );
        succeeded = true;
      } catch {
        // Focus, resync or the next rendered message retries a failed receipt.
      } finally {
        this.pending.delete(key);
        if (succeeded || (this.renderedId !== null && this.renderedId > messageId))
          this.retry();
      }
    })();
  }
}

export function renderedIncomingBoundary(
  messages: Message[],
  userId: number,
  conversationId: number,
  historyLoaded: boolean,
): number | null {
  if (!historyLoaded || messages.some((message) => message.conversation_id !== conversationId))
    return null;
  return messages.reduce<number | null>(
    (lastId, message) => message.sender_id !== userId
      ? Math.max(lastId ?? 0, message.id) : lastId,
    null,
  );
}

export function conversationView(
  messages: Message[],
  messageContext: string,
  loadedContext: string,
  activeContext: string,
) {
  return {
    messages: messageContext === activeContext ? messages : [],
    historyLoaded: loadedContext === activeContext,
  };
}

/** User-wide events keep unopened and newly created conversations up to date. */
export function subscribeConversationEvents(
  url: string,
  onConversation: (conversation: Conversation) => void,
  resync: () => Promise<void>,
) {
  let disposed = false;
  let socket: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let retries = new SocketRetryPolicy();
  const connect = () => {
    if (disposed) return;
    clearTimeout(timer);
    const session = retries.startSession();
    const ws = new WebSocket(url);
    socket = ws;
    ws.onopen = () => {
      if (disposed || socket !== ws) return;
      void resync()
        .then(() => {
          if (!disposed && socket === ws && ws.readyState === WebSocket.OPEN)
            retries.markHealthy(session);
        })
        .catch(() => {
          // Periodic refresh and the next reconnect recover failed snapshots.
        });
    };
    ws.onmessage = (event) => {
      if (disposed || socket !== ws) return;
      let payload: SocketEvent;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload.type === "error" && payload.code === "database_unavailable")
        retries.rejectSession(session);
      if (
        payload.type === "conversation.updated" &&
        payload.data && typeof payload.data === "object" &&
        "other_user" in payload.data
      )
        onConversation(payload.data as Conversation);
    };
    ws.onclose = (event) => {
      if (disposed || socket !== ws) return;
      const delay = retries.nextDelay(session, event.code);
      if (delay !== null) timer = setTimeout(connect, delay);
    };
    ws.onerror = () => { /* onclose owns reconnects. */ };
  };
  connect();
  return {
    reconnect() {
      if (!disposed && (!socket || socket.readyState >= 2)) {
        retries = new SocketRetryPolicy();
        connect();
      }
    },
    close() {
      disposed = true;
      clearTimeout(timer);
      socket?.close();
      socket = null;
    },
  };
}
