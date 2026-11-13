import type { Conversation } from "./types";

type SnapshotRequest = { activityRevision: number; sequence: number };

/** HTTP snapshots must not roll back activity received after the request began. */
export class ConversationActivityGuard {
  private revision = 0;
  private activityRevision = 0;
  private snapshotSequence = 0;
  private appliedSnapshotSequence = 0;

  beginRequest() {
    return this.revision;
  }

  beginSnapshot(): SnapshotRequest {
    return {
      activityRevision: this.activityRevision,
      sequence: ++this.snapshotSequence,
    };
  }

  recordActivity() {
    this.revision += 1;
    this.activityRevision += 1;
  }

  applySnapshot(
    current: Conversation[],
    snapshot: Conversation[],
    request: SnapshotRequest,
  ) {
    if (
      request.activityRevision === this.activityRevision &&
      request.sequence >= this.appliedSnapshotSequence
    ) {
      // Accepted lists invalidate earlier read/TTL/create responses, while a
      // newer list issued at the same live activity revision remains eligible.
      if (request.sequence > this.appliedSnapshotSequence) this.revision += 1;
      this.appliedSnapshotSequence = request.sequence;
      return snapshot;
    }
    const knownIds = new Set(current.map((item) => item.id));
    const missing = snapshot.filter((item) => !knownIds.has(item.id));
    // Conversations cannot be deleted, so an older list may safely fill missing IDs.
    return missing.length ? [...current, ...missing].sort(
      (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
    ) : current;
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
