import type { Conversation } from "./types";

/** HTTP snapshots must not roll back activity received after the request began. */
export class ConversationActivityGuard {
  private revision = 0;

  beginRequest() {
    return this.revision;
  }

  recordActivity() {
    this.revision += 1;
  }

  applySnapshot(
    current: Conversation[],
    snapshot: Conversation[],
    requestRevision: number,
  ) {
    return requestRevision === this.revision ? snapshot : current;
  }

  applyConversationResponse(
    current: Conversation[],
    response: Conversation,
    requestRevision: number,
  ) {
    if (
      requestRevision !== this.revision &&
      current.some((item) => item.id === response.id)
    )
      return current;
    return [...current.filter((item) => item.id !== response.id), response];
  }
}
