# 单聊聊天原型设计规格

## 目标

交付一个可本地运行的 Telegram 风格单聊原型。用户可以用用户名搜索其他用户，发起或进入唯一的双人会话，发送实时消息，并按会话设置消息自动过期删除时间。

首版以功能闭环和交互可验证为目标。暂不实现群聊、频道、文件传输、语音/视频、消息回复、消息编辑、推送通知和生产级身份认证。

## 技术方案

- 后端：Python 3.11+、Sanic、Tortoise ORM、aiomysql。
- 数据库：MySQL 8.0+。本地通过 Docker Compose 启动，数据库连接通过环境变量提供。
- 实时通信：Sanic 原生 WebSocket；HTTP 用于搜索、会话列表、历史消息和 TTL 设置。
- 前端：React + Vite + TypeScript，使用原生 WebSocket 和 `fetch` 调用后端。
- 测试：pytest、pytest-asyncio、Sanic 测试客户端；测试数据库使用 SQLite 临时库以保持测试快速和隔离。

## 原型期身份方案

首版不实现密码注册和 JWT。后端提供固定的演示用户种子数据，HTTP 请求通过 `X-User-Id` 头部识别当前用户，WebSocket 通过 `user_id` 查询参数识别当前用户。前端在左上角提供演示用户切换器，默认选择第一个种子用户。

所有资源访问都必须校验当前用户属于目标会话。该方案只用于本地原型，后续替换为 JWT 时不改变会话和消息 API 的响应结构。

## 数据模型

### User

- `id`：自增主键。
- `username`：用户展示用用户名。
- `username_lower`：小写、唯一索引，用于大小写不敏感搜索。
- `display_name`：展示名称。
- `avatar_url`：可为空。
- `created_at`：创建时间。

### Conversation

- `id`：自增主键。
- `user_a_id`、`user_b_id`：两个用户 ID，始终保存较小 ID 在前。
- `ttl_seconds`：可为空；为空表示关闭自动过期。
- `created_at`、`updated_at`：创建和最后活动时间。
- 约束：`(user_a_id, user_b_id)` 唯一，且两个用户不能相同。

### Message

- `id`：自增主键。
- `conversation_id`：所属会话。
- `sender_id`：发送者。
- `body`：纯文本消息，长度 1-4000 个 Unicode 字符。
- `created_at`：创建时间。
- `expires_at`：可为空；根据发送时会话的 TTL 计算。

消息读取查询必须过滤 `expires_at IS NULL OR expires_at > now`。清理任务每 60 秒删除 `expires_at <= now` 的消息。修改会话 TTL 只影响之后发送的新消息，已有消息保留原有到期时间，避免设置变更导致不可预期的批量删除。

TTL 可选值：关闭、1 小时、1 天、7 天、30 天。API 使用 `null` 表示关闭，其他值使用秒数传输。发送消息时由服务端计算 `expires_at`，客户端不能传入过期时间。

## HTTP API

所有接口前缀为 `/api`，除健康检查外都要求 `X-User-Id`。

### `GET /api/health`

返回 `{ "status": "ok" }`，用于前端启动检查和容器健康检查。

### `GET /api/me`

返回当前演示用户的基础资料。

### `GET /api/users/search?q=<text>`

按 `username_lower` 前缀或包含关系搜索，最少 2 个字符，最多返回 20 个结果。结果排除当前用户，返回 `id`、`username`、`display_name`、`avatar_url`。

### `GET /api/conversations`

返回当前用户参与的会话，按 `updated_at DESC` 排序。每项包含会话 ID、对方用户资料、最后一条未过期消息摘要、未读数（首版固定为 0）和当前 TTL。

### `POST /api/conversations`

请求体：`{ "user_id": 2 }`。按用户 ID 排序查找或创建唯一单聊，返回完整会话对象。对已存在会话重复调用必须幂等。

### `GET /api/conversations/{conversation_id}/messages?limit=50&before=<message_id>`

校验当前用户属于会话后，返回未过期消息，默认最多 50 条，按时间正序返回。`before` 用于向上翻页。

### `PATCH /api/conversations/{conversation_id}/ttl`

请求体：`{ "ttl_seconds": null | 3600 | 86400 | 604800 | 2592000 }`。更新会话 TTL 并返回新的会话对象。

## WebSocket 协议

连接地址：`/ws/conversations/{conversation_id}?user_id=<id>`。连接建立时校验用户属于会话；非法用户收到错误事件后立即关闭。

客户端发送：

```json
{ "type": "message.send", "body": "你好" }
```

服务端广播：

```json
{
  "type": "message.created",
  "data": {
    "id": 101,
    "conversation_id": 5,
    "sender_id": 1,
    "body": "你好",
    "created_at": "2026-11-11T10:00:00Z",
    "expires_at": "2026-11-12T10:00:00Z"
  }
}
```

服务端错误使用 `{ "type": "error", "code": "...", "message": "..." }`。清理任务删除仍在连接中的消息时广播 `message.deleted`，客户端从当前列表移除对应消息。重连后客户端通过历史消息接口补齐状态。

## 后端结构

```text
backend/
  app/
    __init__.py
    config.py          # 环境变量与 TTL 常量
    models.py          # Tortoise 模型
    schemas.py         # 请求/响应 DTO 与校验
    services.py        # 用户搜索、会话、消息和过期清理逻辑
    http_api.py        # Sanic HTTP 路由
    websocket.py       # WebSocket 连接与事件广播
    cleanup.py         # 每 60 秒清理过期消息
    app.py             # Sanic app、Tortoise 初始化和生命周期
  tests/
    test_users.py
    test_conversations.py
    test_messages.py
    test_websocket.py
```

服务层负责权限校验和业务规则，路由层只负责解析请求、调用服务和序列化响应。WebSocket 管理器按会话 ID 保存连接集合，发送消息后只向该会话连接广播。

## 前端结构

```text
frontend/
  src/
    api.ts
    types.ts
    App.tsx
    components/
      UserSwitcher.tsx
      SearchPanel.tsx
      ConversationList.tsx
      ChatHeader.tsx
      MessageList.tsx
      MessageComposer.tsx
      TtlPopover.tsx
    styles.css
```

页面采用三段式桌面布局：左侧窄栏为产品标识和演示用户切换，中间为搜索和会话列表，右侧为聊天区。未选中会话时显示空状态；选中会话后加载历史消息并建立 WebSocket。搜索结果提供“开始聊天”按钮，TTL 弹层提供五个选项并在保存后更新顶部状态。

## 错误处理

- 用户搜索少于 2 个字符返回空列表，不触发数据库模糊查询。
- 消息正文去除首尾空格，空正文或超过 4000 字符返回 400。
- 会话不存在、用户不属于会话、WebSocket 非法连接统一返回 404/403 语义错误。
- WebSocket 断线时前端显示“已断开”，指数退避重连最多 5 次；重连成功后重新拉取历史消息。
- 数据库不可用时 HTTP 返回 503，前端保留当前输入内容并提示稍后重试。

## 验证标准

1. 可以启动 MySQL、Sanic API 和 Vite 前端，并通过健康检查。
2. 演示用户可以按用户名搜索并幂等创建单聊。
3. 两个浏览器窗口使用不同演示用户时，WebSocket 消息能实时到达对方。
4. 历史消息接口不返回已过期消息；清理任务能从数据库删除已过期消息并广播删除事件。
5. 修改 TTL 后，新消息使用新 TTL，已有消息的到期时间不变。
6. pytest 覆盖用户名搜索、会话唯一性、权限校验、TTL 计算、过期过滤和 WebSocket 广播。

## 明确不做的内容

首版不包含真实注册登录、密码找回、联系人列表、群聊、文件上传、端到端加密、消息撤回、已读回执、消息推送和多端同步。这些能力在数据模型和 API 前缀上保留扩展空间，但不进入当前实现范围。
