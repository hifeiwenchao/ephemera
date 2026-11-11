# 轻语 Whisper

一个可以本地运行的 Telegram 风格单聊全栈原型。界面使用 React + TypeScript，后端严格采用 **Python + Sanic + Tortoise ORM + MySQL**，长连接使用 **WebSocket**。

## 已实现

- 根据用户名搜索用户，支持大小写不敏感与可选 `@` 前缀。
- 两名用户之间只有一个单聊；重复发起对话进入已有会话。
- WebSocket 双向发送纯文本消息，历史消息分页加载，断线重连后重新同步。
- 会话可设置关闭、1 小时、1 天、7 天、30 天自动删除。
- 到期消息立即从查询结果中隐藏，前端按到期时间移除；后台每 60 秒物理删除并通知双方。
- 按会话保留未发送草稿，服务端确认后再清空输入。
- 响应式布局，支持桌面和手机宽度。

## 一条命令启动

需要 Docker 与 Docker Compose v2。进入项目根目录后运行：

```bash
docker compose up --build -d
```

打开 **http://127.0.0.1:5174**。首次构建需要拉取 Python、Node、Nginx、MySQL 镜像并安装依赖。后端会创建数据表和演示数据，之后的启动保留已有内容。

```bash
docker compose ps
docker compose logs -f api
docker compose stop
```

默认端口：网页 `5174`、API `8001`、MySQL `3307`，均绑定本机回环地址。MySQL 数据持久化到 Compose 命名卷。避免使用 `down -v`，该命令会移除原型数据库。

Docker 镜像已设置 ARM OpenSSL 兼容选项，在旧版 Docker Desktop 的 ARM 虚拟机中使用便携式加密实现，避免 MySQL 8 认证初始化触发不支持的硬件指令。该选项可能降低 ARM 上的加密计算性能，认证协议保持不变。

## 开发启动

需要 Python 3.11+、Node.js 22.12+，数据库为 MySQL 8.0+。本项目已用 Python 3.11、MySQL 8.0、Node 24 完成联调。

### 1. 数据库

```bash
cp backend/.env.example backend/.env
docker compose --env-file backend/.env up -d mysql
```

默认开发数据库地址为 `mysql://chat:chat_password@127.0.0.1:3307/single_chat`。要修改数据库端口，需同时修改 `MYSQL_PORT` 和 `DATABASE_URL`。后端固定从 `backend/.env` 读取配置，系统环境变量优先。

### 2. Python 后端

在项目根目录执行：

```bash
python3.11 -m venv work/venv
source work/venv/bin/activate
python -m pip install -e './backend[dev]'
python -m backend.app.app
```

服务默认监听 http://127.0.0.1:8001。MySQL 8 默认认证所需的 `cryptography` 已包含在项目依赖中。启动时自动创建缺失表；当前原型未包含生产数据库迁移流程。

### 3. React 前端

在另一终端执行：

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 http://127.0.0.1:5173。Vite 将 `/api` 和 `/ws` 代理到 `8001`，通常无需额外配置。

## 体验双人聊天

首次启动预置 `alice / 艾莉丝`、`bob / 林间`、`carol / 陈沐`、`david / 顾远`、`nina / 宁可`，并为 Alice 提供几段示例聊天。

1. 打开两个网页窗口。
2. 点击左下角头像，第一个窗口选择 Alice，第二个窗口选择 Bob。
3. 在第一个窗口搜索 `@bob`，点击开始聊天；第二个窗口进入与 Alice 的会话。
4. 任一窗口发送消息，另一个窗口会通过 WebSocket 实时收到。
5. 点击聊天顶部的自动删除设置，选择 `1 小时`，双方都会立即看到设置更新。
6. 之后发送的消息带有到期时间；已有消息的到期时间保持原样。

本原型使用演示身份切换，没有密码注册登录。HTTP 使用 `X-User-Id`，WebSocket 使用 `user_id` 参数；这是可替换的本地演示身份方案，**并非生产认证**。目前使用单进程连接管理器，启动入口已设置单进程。

## 自动删除语义

TTL 从服务端接受消息的时刻开始计时。TTL 设置只影响之后发送的新消息；关闭 TTL 不会撤销已有消息的到期时间。所有时间在数据库和 API 内以 UTC 存储和传输，界面按浏览器时区展示。

消息过期时，历史查询不再返回该消息。客户端每秒移除已到期内容；清理任务默认每 60 秒从 MySQL 物理删除，并广播 `message.deleted`。因此到期记录最多再保留一个清理周期。清理间隔可通过 `CLEANUP_INTERVAL_SECONDS` 调整。

## API 与协议

除 `/api/health`、`/api/demo-users` 外均要求 `X-User-Id`。

| 方法 | 地址 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务与数据库健康检查 |
| GET | `/api/demo-users` | 演示身份列表 |
| GET | `/api/me` | 当前用户 |
| GET | `/api/users/search?q=bob` | 搜索用户名，至少 2 字符 |
| GET | `/api/conversations` | 会话列表 |
| POST | `/api/conversations` | 请求体 `{"user_id": 2}`，幂等创建会话 |
| GET | `/api/conversations/1/messages?limit=50&before=100` | 未过期消息历史，正序返回 |
| PATCH | `/api/conversations/1/ttl` | 请求体 `{"ttl_seconds": 3600}`，关闭用 `null` |

WebSocket：`ws://127.0.0.1:8001/ws/conversations/1?user_id=1`。

```json
{"type":"message.send","body":"你好"}
```

服务端事件：

```json
{"type":"message.created","data":{"id":101,"conversation_id":1,"sender_id":1,"body":"你好","created_at":"2026-11-11T08:00:00Z","expires_at":null}}
{"type":"message.deleted","data":{"ids":[101]}}
{"type":"conversation.updated","data":{"id":1,"ttl_seconds":3600}}
{"type":"error","code":"validation_error","message":"消息长度必须为 1–4000 个字符"}
```

历史和搜索接口返回 JSON 数组。会话字段为 `id`、`other_user`、`ttl_seconds`、`last_message`、`created_at`、`updated_at`、`unread_count`（原型固定为 0）。

## 配置

| 变量 | 默认值 | 用途 |
|---|---|---|
| `DATABASE_URL` | `mysql://chat:chat_password@127.0.0.1:3307/single_chat` | 开发数据库连接 |
| `HOST` / `PORT` | `127.0.0.1` / `8001` | 开发 API 监听 |
| `CLEANUP_INTERVAL_SECONDS` | `60` | 物理删除周期 |
| `CORS_ORIGINS` | `http://localhost:5173` | 允许的跨域来源，逗号分隔 |
| `MYSQL_PORT` | `3307` | Compose MySQL 宿主机端口 |
| `API_PORT` / `WEB_PORT` | `8001` / `5174` | Compose API 和网页端口 |

Docker 模式的后端自动使用 Compose 网络内的 MySQL 地址。Vite 与 Nginx 默认通过同源代理访问 API；若单独部署前端，可使用 `VITE_API_BASE_URL` 与 `VITE_WS_BASE_URL` 指定接口地址。

## 测试

在项目根目录：

```bash
work/venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

后端使用隔离 SQLite 测试数据库，覆盖搜索、会话唯一性、权限、TTL 快照、过期过滤、HTTP 输入、两个真实 WebSocket 客户端与定时物理删除。另已在实际 MySQL 8 环境验证 UTF-8 表情、双向广播、TTL 保留规则和后台清理。

当前只实现文本单聊；真实认证、群聊、附件、已读回执与推送未进入此原型范围。发送失败或未收到服务端确认时保留草稿；网络确认丢失后的手动重发可能产生重复消息，生产版本可加入客户端消息 ID 去重。
