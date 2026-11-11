import type { Message } from "../types";

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
