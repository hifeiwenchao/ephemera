# 单聊聊天原型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个可本地运行的 Telegram 风格单聊原型，支持用户名搜索、唯一单聊、WebSocket 实时消息和按会话 TTL 自动删除消息。

**Architecture:** 使用 Sanic 提供 HTTP/WebSocket API，Tortoise ORM 负责 MySQL 访问；业务规则集中在服务层，路由层只处理传输和序列化。React + Vite 前端通过 HTTP 加载数据、通过 WebSocket 接收实时事件，首版用演示用户切换器替代真实认证。

**Tech Stack:** Python 3.11、Sanic、Tortoise ORM、aiomysql、MySQL 8、pytest、React、Vite、TypeScript、原生 WebSocket。

**Spec:** `docs/superpowers/specs/2026-11-11-single-chat-design.md`

## Global Constraints

- 后端必须使用 Python + Sanic + Tortoise ORM；数据库必须使用 MySQL 8，连接配置来自环境变量。
- 所有受保护 HTTP 请求使用 `X-User-Id`；WebSocket 使用 `user_id` 查询参数，当前只用于演示认证。
- 会话是严格双人单聊，两个用户 ID 排序后建立唯一约束；不实现群聊。
- TTL 只影响设置后的新消息；读取接口过滤已过期消息，后台每 60 秒物理删除过期消息。
- 消息正文去除首尾空格，长度限制为 1-4000 个 Unicode 字符。
- 代码和测试中统一使用 UTC-aware datetime，API 使用 ISO 8601 字符串。
- 提交信息使用 `feature: 中文说明`、`fix: 中文说明` 或 `refactor: 中文说明` 格式。

---

### Task 1: 建立项目脚手架、配置和本地 MySQL

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/.env.example`
- Create: `docker-compose.yml`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `README.md`

**Interfaces:**
- Produces `backend.app.config.Settings`, whose fields are `database_url: str`, `debug: bool`, `cleanup_interval_seconds: int`, and `cors_origins: list[str]`.
- Produces a Compose service named `mysql` exposing port `3306` with database `single_chat`, user `chat`, and password `chat_password` for local development.

- [ ] **Step 1: Write the failing configuration test**

Create `backend/tests/test_config.py`:

```python
from backend.app.config import Settings


def test_settings_reads_database_url_and_cleanup_interval(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://chat:secret@localhost:3306/single_chat")
    monkeypatch.setenv("CLEANUP_INTERVAL_SECONDS", "15")
    settings = Settings.from_env()
    assert settings.database_url.endswith("/single_chat")
    assert settings.cleanup_interval_seconds == 15
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_config.py -q`

Expected: FAIL because `backend.app.config` does not exist.

- [ ] **Step 3: Add the Python package metadata and configuration loader**

Define `Settings.from_env()` in `backend/app/config.py`, defaulting to `mysql://chat:chat_password@127.0.0.1:3306/single_chat`, `debug=False`, `cleanup_interval_seconds=60`, and `cors_origins=["http://localhost:5173"]`. Add runtime dependencies for Sanic, Tortoise ORM with MySQL support, pydantic, and python-dotenv; add pytest, pytest-asyncio, and sanic-testing under the development group.

- [ ] **Step 4: Add local services and frontend metadata**

Create `docker-compose.yml` with MySQL 8.0, a health check using `mysqladmin ping`, a named volume, and the environment variables from `.env.example`. Create the Vite React TypeScript package files with scripts `dev`, `build`, and `preview`. Keep the initial Vite entry minimal so later tasks can replace it.

- [ ] **Step 5: Run the configuration test and install dependencies**

Run: `cd backend && python -m pytest tests/test_config.py -q`

Expected: PASS. Then run `python -m pip install -e .` from `backend` and `npm install` from `frontend`.

- [ ] **Step 6: Document local startup and commit**

Document `docker compose up -d mysql`, `python -m backend.app.app`, and `npm run dev` in `README.md`.

```bash
git add backend frontend docker-compose.yml README.md
git commit -m "feature: 建立单聊原型项目脚手架"
```

### Task 2: 实现 Tortoise 数据模型、DTO 和演示用户种子

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/schemas.py`
- Create: `backend/app/db.py`
- Create: `backend/app/seed.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_models.py`

**Interfaces:**
- Produces Tortoise models `User`, `Conversation`, and `Message` with the fields defined in the spec.
- Produces `init_db(database_url: str, generate_schemas: bool = False)` and `close_db()`.
- Produces DTO helpers `user_to_dict`, `conversation_to_dict`, `message_to_dict` and `parse_ttl_seconds(value)`.

- [ ] **Step 1: Write failing model and DTO tests**

In `backend/tests/test_models.py`, configure an in-memory SQLite Tortoise test database and add tests for sorted conversation participants, duplicate participant rejection, valid TTL values, invalid TTL rejection, and message expiry calculation:

```python
import pytest
from datetime import datetime, timezone, timedelta
from backend.app.schemas import parse_ttl_seconds


def test_parse_ttl_seconds_accepts_supported_values():
    assert parse_ttl_seconds(None) is None
    assert parse_ttl_seconds(3600) == 3600


def test_parse_ttl_seconds_rejects_unsupported_value():
    with pytest.raises(ValueError):
        parse_ttl_seconds(30)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_models.py -q`

Expected: FAIL because models and schema helpers are missing.

- [ ] **Step 3: Implement models and relationships**

Define `User` with a unique `username_lower`; `Conversation` with `user_a`, `user_b`, `ttl_seconds`, timestamps and a unique constraint on both user columns; and `Message` with foreign keys, body, timestamps and nullable `expires_at`. Add indexes for `Conversation.updated_at`, `Message.conversation_id`, and `Message.expires_at`.

- [ ] **Step 4: Implement DTO validation and database lifecycle**

Use explicit dictionaries/dataclasses for API responses. `parse_ttl_seconds` must allow only `None`, `3600`, `86400`, `604800`, and `2592000`. `init_db` must register the three models, optionally generate schemas for tests, and `close_db` must close connections. `seed.py` must create `alice`, `bob`, and `carol` idempotently.

- [ ] **Step 5: Run model tests and commit**

Run: `cd backend && python -m pytest tests/test_config.py tests/test_models.py -q`

Expected: PASS with all tests green.

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/db.py backend/app/seed.py backend/tests
git commit -m "feature: 添加单聊数据模型和演示用户"
```

### Task 3: 实现服务层和 HTTP API

**Files:**
- Create: `backend/app/services.py`
- Create: `backend/app/http_api.py`
- Create: `backend/app/errors.py`
- Create: `backend/tests/test_users.py`
- Create: `backend/tests/test_conversations.py`
- Create: `backend/tests/test_messages.py`

**Interfaces:**
- Produces `search_users(current_user_id, query)`, `get_or_create_conversation(current_user_id, other_user_id)`, `list_conversations(current_user_id)`, `list_messages(current_user_id, conversation_id, limit, before_id)`, `set_conversation_ttl(current_user_id, conversation_id, ttl_seconds)`, and `create_message(current_user_id, conversation_id, body)`.
- Produces Sanic routes: `GET /api/health`, `GET /api/me`, `GET /api/users/search`, `GET /api/conversations`, `POST /api/conversations`, `GET /api/conversations/{id}/messages`, and `PATCH /api/conversations/{id}/ttl`.

- [ ] **Step 1: Write failing service tests**

Cover case-insensitive user search excluding the current user, idempotent conversation creation, forbidden access for non-participants, body trimming and length validation, TTL calculation, and filtering expired messages. Example:

```python
async def test_create_conversation_is_idempotent(test_users):
    first = await get_or_create_conversation(test_users.alice.id, test_users.bob.id)
    second = await get_or_create_conversation(test_users.bob.id, test_users.alice.id)
    assert first.id == second.id
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_users.py tests/test_conversations.py tests/test_messages.py -q`

Expected: FAIL because service functions and routes are missing.

- [ ] **Step 3: Implement service helpers and error types**

Add a `NotFoundError`, `ForbiddenError`, and `ValidationError` mapped to HTTP status codes. Each service function must fetch the current user, verify conversation membership, and return DTO dictionaries. `create_message` must calculate `expires_at` from the current conversation TTL and update `Conversation.updated_at`.

- [ ] **Step 4: Implement HTTP routes and current-user extraction**

Add `require_user_id(request)` to parse `X-User-Id`, returning 401 for missing or unknown users. Parse JSON bodies with explicit type checks, return 400 for invalid inputs, and serialize errors as `{ "error": { "code": "...", "message": "..." } }`. Use `limit` bounds 1-100 and validate positive integer `before` values.

- [ ] **Step 5: Run API tests and commit**

Run: `cd backend && python -m pytest tests/test_users.py tests/test_conversations.py tests/test_messages.py -q`

Expected: PASS. Add route-level assertions for status codes and response shapes using the Sanic test client.

```bash
git add backend/app/services.py backend/app/http_api.py backend/app/errors.py backend/tests
git commit -m "feature: 增加用户搜索会话和消息接口"
```

### Task 4: 实现 WebSocket 实时消息和过期清理

**Files:**
- Create: `backend/app/websocket.py`
- Create: `backend/app/cleanup.py`
- Create: `backend/app/app.py`
- Create: `backend/tests/test_websocket.py`
- Create: `backend/tests/test_cleanup.py`

**Interfaces:**
- Produces `ConnectionManager.connect(conversation_id, websocket)`, `disconnect(...)`, and `broadcast(conversation_id, event)`.
- Produces `cleanup_expired_messages(now=None) -> int` and `cleanup_loop(app)`.
- Produces `create_app(settings=None) -> Sanic` with database lifecycle, HTTP routes, WebSocket routes, seed initialization, and cleanup task.

- [ ] **Step 1: Write failing cleanup and WebSocket tests**

Test that `cleanup_expired_messages` deletes expired rows but keeps non-expired rows, and that two connected test clients receive a `message.created` event after one client sends `message.send`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_cleanup.py tests/test_websocket.py -q`

Expected: FAIL because the manager, cleanup function and Sanic app do not exist.

- [ ] **Step 3: Implement the connection manager**

Store `dict[int, set[WebsocketConnection]]`. On broadcast, send JSON to each connection and remove connections that raise a send/connection error. WebSocket handler must validate `user_id`, verify conversation membership, accept `message.send`, call `create_message`, and broadcast `message.created`.

- [ ] **Step 4: Implement cleanup and app lifecycle**

Delete `Message` rows where `expires_at <= utcnow`, collect deleted IDs by conversation, and broadcast `message.deleted` for active connections. Start an asyncio task in Sanic `before_server_start` and cancel it in `after_server_stop`; use `CLEANUP_INTERVAL_SECONDS` from settings. Register CORS for the configured frontend origin.

- [ ] **Step 5: Run backend tests and commit**

Run: `cd backend && python -m pytest -q`

Expected: PASS for configuration, models, HTTP, cleanup, and WebSocket tests.

```bash
git add backend/app backend/tests
git commit -m "feature: 增加 WebSocket 聊天和消息过期清理"
```

### Task 5: 构建前端聊天壳和用户名搜索

**Files:**
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/components/UserSwitcher.tsx`
- Create: `frontend/src/components/SearchPanel.tsx`
- Create: `frontend/src/components/ConversationList.tsx`
- Create: `frontend/src/components/ChatHeader.tsx`
- Create: `frontend/src/components/MessageList.tsx`
- Create: `frontend/src/components/MessageComposer.tsx`
- Create: `frontend/src/components/TtlPopover.tsx`
- Create: `frontend/src/styles.css`
- Modify: `frontend/index.html`

**Interfaces:**
- `api.ts` exports `searchUsers`, `listConversations`, `createConversation`, `listMessages`, `updateConversationTtl`, and `getMe` with the `X-User-Id` header.
- `App.tsx` owns `currentUserId`, `conversations`, `selectedConversationId`, search results, messages, loading state, and error state.

- [ ] **Step 1: Add frontend type definitions and API tests**

Create `frontend/src/types.ts` for `User`, `Conversation`, `Message`, and `TtlSeconds`. Add Vitest as a dev dependency and a `test` script to `frontend/package.json`, then write a fetch mock test asserting `searchUsers` sends the correct query and `X-User-Id` header.

- [ ] **Step 2: Implement the API client and basic app shell**

Create `api.ts` with a configurable `VITE_API_BASE_URL`, typed JSON parsing, and a shared error parser. Render the three-column layout with empty states and a loading skeleton.

- [ ] **Step 3: Implement user switching, search and conversation list**

The user switcher uses seeded IDs 1, 2, and 3. Search starts only at two characters, debounced by 250ms, and clicking a result calls `createConversation`, refreshes the list, and selects the conversation.

- [ ] **Step 4: Implement message list, composer and TTL popover**

Render incoming and outgoing bubbles with timestamps and an expiration badge when TTL is enabled. The composer trims on submit, disables while sending, and keeps its text on HTTP failure. The TTL popover calls `updateConversationTtl` and updates the selected conversation in local state.

- [ ] **Step 5: Run frontend checks and commit**

Run: `cd frontend && npm run test -- --run`

Expected: PASS with the API client test green. Also run `npm run build` to verify the production bundle and TypeScript types.

```bash
git add frontend
git commit -m "feature: 构建单聊搜索和会话界面"
```

### Task 6: 接入 WebSocket、重连和端到端验证

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/MessageList.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/useConversationSocket.ts`
- Create: `backend/tests/test_integration.py`
- Modify: `README.md`

**Interfaces:**
- `useConversationSocket(conversationId, userId, onEvent)` opens `VITE_WS_BASE_URL`, returns `{ status, sendMessage, close }`, and invokes `onEvent` for `message.created`, `message.deleted`, and `error`.

- [ ] **Step 1: Write the failing socket hook and integration tests**

Test that selecting a conversation opens the WebSocket, incoming `message.created` appends exactly once, and `message.deleted` removes the matching message. Add a backend integration test that starts the app, creates a conversation, sends one message over WebSocket, and reads it back over HTTP.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_integration.py -q` and `cd frontend && npm run build`

Expected: integration test fails because the hook and complete app wiring are missing; frontend build may fail on missing imports.

- [ ] **Step 3: Implement the WebSocket hook and state reconciliation**

Open a socket only for the selected conversation. On open, mark status `connected`; on close, retry with 500ms, 1s, 2s, 4s, and 8s delays up to five times. After reconnect, refetch history and merge by message ID. When sending, call `socket.send(JSON.stringify({ type: "message.send", body }))`.

- [ ] **Step 4: Add connection status and expiration feedback**

Show `实时`/`重连中`/`已断开` in `ChatHeader`, remove deleted bubbles immediately, and show an unobtrusive toast when a message expires. Ensure switching conversations closes the previous socket.

- [ ] **Step 5: Run full verification**

Run:

```bash
docker compose up -d mysql
cd backend && python -m pytest -q
cd ../frontend && npm run build
```

Expected: all backend tests pass, the frontend build succeeds, and manual verification with two browser windows confirms real-time delivery and TTL deletion.

- [ ] **Step 6: Document the final runbook and commit**

Update `README.md` with environment setup, demo user IDs, API/WebSocket URLs, TTL behavior, test commands, and the two-window manual verification flow.

```bash
git add backend frontend README.md
git commit -m "feature: 完成单聊实时聊天原型"
```

## Verification Checklist

- [ ] `docker compose up -d mysql` starts a healthy MySQL container.
- [ ] `cd backend && python -m pytest -q` passes all tests.
- [ ] `cd frontend && npm run build` passes without TypeScript errors.
- [ ] `GET /api/health` returns `{ "status": "ok" }`.
- [ ] Search excludes the current user and starts at two characters.
- [ ] Creating the same pair twice returns one conversation ID.
- [ ] Non-participants cannot read messages or update TTL.
- [ ] WebSocket messages arrive in both connected clients.
- [ ] TTL affects new messages, and expired messages disappear from history and storage.
