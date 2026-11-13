# Unread state repair

**Goal:** Incoming messages update each recipient's conversation badge, and viewing a conversation clears only messages the client has loaded.

**Cause:** The conversation DTO returns a constant zero; the list never renders the field; sockets subscribe only to the selected conversation.

**Architecture:** Store a monotonic read cursor per conversation and user in Redis. Count live messages from the other participant after that cursor. Keep existing conversation sockets and add an authenticated user event stream for full conversation DTOs. Use an explicit read acknowledgement after rendering in the visible, focused conversation.

**Constraints:** Preserve Redis native message TTL, cookie authentication, existing conversation WebSocket events, and SQL schema. Do not mark a history fetch as read. Do not let a delayed HTTP response overwrite newer activity. Work directly in the current clean checkout; do not commit or publish.

## Backend

- [x] Reproduce the constant-zero bug with a failing service test: Alice sends one message, Alice has zero unread and Bob has one.
- [x] Add Redis cursor advancement with WATCH, accepting only a message ID indexed in the requested conversation. Verify older read acknowledgements cannot lower the cursor and later messages remain unread.
- [x] Allocate message IDs and commit message bodies/history atomically, so concurrent insertion cannot place a previously unseen message behind an acknowledged cursor.
- [x] Count only live messages after the cursor from the other participant; verify expiry before and after cleanup.
- [x] Add `POST /api/conversations/<id>/read` with `{"last_message_id": 101}` and a full conversation response. Reject nonmembers, malformed IDs and IDs from another conversation.
- [x] Add `/ws/events` with existing cookie authentication. Publish `conversation.updated` with each recipient's full conversation DTO after message creation, TTL changes, read acknowledgement and expiry cleanup.
- [x] Verify real sockets receive inactive/new conversation updates and read state changes without altering existing conversation socket events.

Files: `backend/app/message_store.py`, `schemas.py`, `services.py`, `websocket.py`, `http_api.py`, `cleanup.py`; matching tests under `backend/tests/`.

## Frontend

- [x] Write failing tests for unread badges, incoming conversation upserts and read eligibility/order.
- [x] Add the user event socket with reconnect and snapshot resync. Preserve the activity guard against stale HTTP responses.
- [x] Render an accessible unread badge in each conversation and style it within the existing list layout.
- [x] Acknowledge the last rendered incoming message only in the selected, loaded, visible and focused conversation. Retry failed acknowledgements without clearing unread optimistically or applying stale responses.
- [x] Verify switching conversations and hidden tabs cannot acknowledge unseen messages.

Files: `frontend/src/api.ts`, `App.tsx`, `conversationState.ts`, `components/ConversationList.tsx`, `components/MessageList.tsx`, `hooks/`, `styles.css`; matching Vitest tests.

## Integration and verification

- [x] Review backend/frontend contract and concurrency handling independently.
- [x] Update README with unread semantics, read endpoint and user event stream.
- [x] Run `work/venv/bin/python -m pytest backend/tests -q`, `npm test`, `npm run build`, and `git diff --check`.
- [x] Rebuild the already running local `api` and `web` Compose services and verify health and local UI.

Validation: backend 122 passed; frontend 51 passed; production build passed; Compose api/web rebuilt and started; /api/health returned ok; local UI reloaded with a connected conversation. Independent review found no remaining material issues.

## Follow-up: outgoing message read receipts

The user identified the outgoing message checkmark in a screenshot. Extend the existing read cursor to sender-visible receipts, using one check for sent and two for peer-read.

- [x] Add `other_last_read_message_id: number | null` to each participant's conversation DTO, reading the other participant's Redis cursor.
- [x] Notify both participants on a read acknowledgement; test direction, monotonicity and real sender events with reconnect persistence.
- [x] Render single/double checkmarks for outgoing messages and own-message conversation previews; compare each ID to the peer cursor and keep incoming messages free of outgoing status icons.
- [x] Test absent cursor, exact read boundary, later unread messages and delayed snapshot protection.
- [x] Run full backend/frontend tests, build, independent review and diff checks; rebuild local services and inspect the UI.

Receipt validation: backend 123 passed; frontend 63 passed; build and diff checks passed; local api/web rebuilt and healthy. Browser inspection after reload found four outgoing receipts labelled 对方已读 and visibly rendered as double checks. Independent review found no material issues.
