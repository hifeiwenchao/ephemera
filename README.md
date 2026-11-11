# Ephemera

一个可以本地运行的 Telegram 风格单聊全栈原型。界面使用 React + TypeScript，后端采用 **Python + Sanic + Tortoise ORM + MySQL + Redis**，长连接使用 **WebSocket**。用户资料和会话设置保存在 MySQL；消息正文与聊天记录全部保存在 Redis。

## 已实现

- 根据账号名或昵称搜索用户，账号名大小写不敏感，支持可选 `@` 前缀；账号名和昵称均唯一且最多 12 位。账号名可用英文字母、数字和 `!@#$%^&*()-+=~`，昵称可用中英文、数字和 `!@#$%^&*()-+=`。
- 两名用户之间只有一个单聊；重复发起对话进入已有会话。
- WebSocket 双向发送纯文本消息，历史消息分页加载，断线重连后重新同步。
- 会话可设置关闭、1 小时、1 天、7 天、30 天自动删除。
- 到期消息使用 Redis 原生 TTL 过期，前端按到期时间移除；后台定期清理并通知双方。
- 注册必须绑定已验证邮箱；支持用户名密码登录和邮箱验证码登录，登录状态使用 HttpOnly Cookie。
- 当前测试模式不发送真实邮件，验证码固定使用 `666666`；切换真实 SMTP 时关闭 `AUTH_TEST_MODE` 并填写 SMTP 配置。
- 按会话保留未发送草稿，服务端确认后再清空输入。
- 响应式布局，支持桌面和手机宽度。

## 一条命令启动

需要 Docker、Docker Compose v2、已在本机 `3306` 端口运行的 MySQL 8.0+，以及本机 `6379` 端口的 Redis。默认连接现有 MySQL 的 `root` 用户。首次使用先创建应用数据库：

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p
```

```sql
CREATE DATABASE IF NOT EXISTS single_chat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

在项目根目录复制配置，并将 `.env` 中的 MySQL 与 Redis 密码占位符改为实际密码：

```bash
cp .env.example .env
```

Docker 中的 MySQL 地址为 `mysql://root:你的密码@host.docker.internal:3306/single_chat`，Redis 地址为 `redis://default:你的密码@host.docker.internal:6379/0`。两个连接地址的密码若包含 `@`、`:`、`/`、`#`、`%` 等特殊字符，需使用 URL 编码，例如 `@` 写作 `%40`。配置后用一条命令启动：

```bash
docker compose up --build -d api web
```

打开 **http://127.0.0.1:5174**。首次构建需要拉取 Python、Node 和 Nginx 镜像并安装依赖。后端会在 `single_chat` 中创建缺失的用户与会话表，并初始化演示数据；聊天记录写入 Redis。Docker 不会创建外部 MySQL 数据库或启动 Redis 容器。

当前工作目录的私有 `.env` 与 `backend/.env` 已配置。它们不会提交到版本库或包含在交付压缩包中；解压到新目录后，需要重新复制示例并填写密码。

```bash
docker compose ps
docker compose logs -f api
docker compose stop
```

默认端口：网页 `5174`、API `8001`，均绑定本机回环地址；数据服务使用现有本机 MySQL `3306` 与 Redis `6379`。应用停止不会删除外部数据。

消息键使用独立的 `whisper:` 前缀（这是早期原型的兼容前缀，升级为 Ephemera 后保留以避免丢失已有消息）；应用不执行 `FLUSHDB`，不会清空同一 Redis 数据库中的其他键。Redis 服务重启后能否恢复聊天记录，取决于本机 Redis 的 AOF/RDB 持久化设置；项目不会修改已有 Redis 服务的配置。

后端 Docker 镜像已设置 ARM OpenSSL 兼容选项，在旧版 Docker Desktop 的 ARM 虚拟机中使用便携式加密实现，避免 MySQL 8 认证初始化触发不支持的硬件指令。该选项可能降低 ARM 上的加密计算性能，认证协议保持不变。

### 可选：使用内置 MySQL

内置 MySQL 保留为 `bundled-db` profile，默认不启动。如需独立的原型用户与会话数据库，将根目录 `.env` 中的 `DATABASE_URL` 改为 `mysql://chat:chat_password@mysql:3306/single_chat`，保留外部 Redis 的 `REDIS_URL`，再执行：

```bash
docker compose --profile bundled-db up -d --wait mysql
docker compose up --build -d api web
```

内置 MySQL 默认映射到本机回环地址的 `3307` 端口，数据保存在原有 Compose 命名卷中。避免使用 `docker compose down -v`，该命令会移除内置原型数据库。直接运行 Python 后端时，连接内置数据库的地址应为 `mysql://chat:chat_password@127.0.0.1:3307/single_chat`。

## 开发启动

需要 Python 3.11+、Node.js 22.12+、MySQL 8.0+ 和 Redis。

### 1. 数据库

使用本机 `3306` 端口的现有 MySQL 和 `6379` 端口的 Redis，并按上文 SQL 创建 `single_chat`。复制开发配置：

```bash
cp backend/.env.example backend/.env
```

将 `backend/.env` 中的密码占位符改为本机 MySQL 与 Redis 密码，地址分别为 `mysql://root:你的密码@127.0.0.1:3306/single_chat` 与 `redis://default:你的密码@127.0.0.1:6379/0`；密码特殊字符同样需 URL 编码。后端固定从 `backend/.env` 读取配置，系统环境变量优先。根目录 `.env` 仅用于 Docker Compose，不会被直接运行的 Python 后端读取。

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

首次启动预置 `alice / 艾莉丝`、`bob / 林间`、`carol / 陈沐`、`david / 顾远`、`nina / 宁可`，并为 Alice 提供几段示例聊天。预置身份用于保留原型数据；新用户请走注册流程并绑定邮箱。

1. 打开网页，点击“创建账号”。
2. 填写账号名、昵称、密码和邮箱，点击“获取验证码”。
3. 测试环境直接输入验证码 `666666` 完成注册；也可使用同一验证码进行邮箱登录。
4. 打开第二个浏览器窗口注册另一个账号，在搜索框按账号名或昵称找到对方并开始聊天。
5. 任一窗口发送消息，另一个窗口会通过 WebSocket 实时收到。
6. 点击聊天顶部的自动删除设置，选择 `1 小时`；之后发送的消息带有到期时间，已有消息保持原样。

API 默认只接受登录 Cookie；`ALLOW_LEGACY_IDENTITY` 默认为 `false`，仅测试兼容旧演示请求。当前使用单进程连接管理器，启动入口已设置单进程。

## 自动删除语义

TTL 从服务端接受消息的时刻开始计时。TTL 设置只影响之后发送的新消息；关闭 TTL 不会撤销已有消息的到期时间。所有时间在存储和 API 内以 UTC 存储和传输，界面按浏览器时区展示。

设置了到期时间的消息使用 Redis 原生 TTL，到期后历史查询不再返回该消息。客户端每秒移除已到期内容；后台清理任务默认每 60 秒广播 `message.deleted`，执行间隔可通过 `CLEANUP_INTERVAL_SECONDS` 调整。MySQL 不保存消息正文或聊天记录。

## API 与协议

除健康检查和验证码发送外，接口均需要登录 Cookie。

| 方法 | 地址 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务、MySQL 与 Redis 健康检查 |
| POST | `/api/auth/email-code` | 请求邮箱验证码，`purpose` 为 `register` 或 `login` |
| POST | `/api/auth/register` | 账号名、昵称、密码、邮箱和验证码注册，并建立 Cookie 会话 |
| POST | `/api/auth/login/password` | 账号名或邮箱 + 密码登录 |
| POST | `/api/auth/login/email` | 邮箱验证码登录 |
| POST | `/api/auth/logout` | 撤销当前会话并清除 Cookie |
| GET | `/api/me` | 当前用户 |
| GET | `/api/users/search?q=bob` | 搜索账号名或昵称（至少 1 个字符） |
| GET | `/api/conversations` | 会话列表 |
| POST | `/api/conversations` | 请求体 `{"user_id": 2}`，幂等创建会话 |
| GET | `/api/conversations/1/messages?limit=50&before=100` | 未过期消息历史，正序返回 |
| PATCH | `/api/conversations/1/ttl` | 请求体 `{"ttl_seconds": 3600}`，关闭用 `null` |

WebSocket：`ws://127.0.0.1:8001/ws/conversations/1`，浏览器通过同源 Cookie 完成身份认证。

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
| `DATABASE_URL` | `mysql://root@127.0.0.1:3306/single_chat` | 原生开发默认连接；在 `backend/.env` 填写密码。Docker 必须在根目录 `.env` 配置，主机名用 `host.docker.internal` |
| `REDIS_URL` | 在私有配置中填写 | Redis 消息存储连接；原生开发用 `127.0.0.1:6379`，Docker 用 `host.docker.internal:6379` |
| `AUTH_SECRET` | 私有随机值（至少 32 字符） | Cookie 会话签名摘要的服务端密钥 |
| `SESSION_COOKIE_SECURE` | `false` | HTTPS 部署时改为 `true` |
| `AUTH_TEST_MODE` | `true`（当前本地配置） | 测试模式固定接受验证码 `666666`，不发送邮件；真实环境改为 `false` |
| `SMTP_HOST` / `SMTP_PORT` | `127.0.0.1` / `1025` | `AUTH_TEST_MODE=false` 时的验证码 SMTP 服务 |
| `SMTP_FROM` | `no-reply@local.test` | 验证码发件地址 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_STARTTLS` | 空 / 空 / `false` | 切换真实 SMTP 时填写 |
| `ALLOW_LEGACY_IDENTITY` | `false` | 仅测试旧 `X-User-Id`/`user_id` 身份；生产保持关闭 |
| `HOST` / `PORT` | `127.0.0.1` / `8001` | 开发 API 监听 |
| `CLEANUP_INTERVAL_SECONDS` | `60` | 过期清理任务周期 |
| `CORS_ORIGINS` | `http://localhost:5173` | 允许的跨域来源，逗号分隔 |
| `MYSQL_PORT` | `3307` | 可选 `bundled-db` 内置 MySQL 的宿主机端口 |
| `API_PORT` / `WEB_PORT` | `8001` / `5174` | Compose API 和网页端口 |

Docker 模式的后端通过根目录 `.env` 的 `DATABASE_URL` 与 `REDIS_URL` 连接数据服务；原生开发读取 `backend/.env`。Vite 与 Nginx 默认通过同源代理访问 API；若单独部署前端，可使用 `VITE_API_BASE_URL` 与 `VITE_WS_BASE_URL` 指定接口地址。

## 测试

在项目根目录：

```bash
work/venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

后端使用隔离 SQLite 与 fakeredis 测试数据库，覆盖账号名/昵称/邮箱唯一性、昵称规则、邮箱验证码过期/重放/限流、密码与邮箱登录、Cookie 会话、账号名和昵称搜索、会话唯一性、权限、Redis TTL、过期索引、HTTP 输入和两个真实 WebSocket 客户端。另已在实际 MySQL/Redis 环境验证数据迁移、UTF-8 消息、双向广播、原生 TTL 和测试验证码流程。

当前只实现文本单聊；群聊、附件、已读回执与推送未进入此原型范围。发送失败或未收到服务端确认时保留草稿；网络确认丢失后的手动重发可能产生重复消息，生产版本可加入客户端消息 ID 去重。
