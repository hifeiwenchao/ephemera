# Redis 消息与账号认证实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task.

**Goal:** 保留现有聊天数据并接入Redis消息存储、邮箱验证注册与两种登录方式。
**Architecture:** MySQL保存账号和会话元数据，Redis保存消息、验证码和登录会话。前端使用HttpOnly cookie身份，邮件进入本机Mailpit。
**Tech Stack:** Sanic/Tortoise/MySQL/Redis/React/TypeScript/Mailpit。
**Spec:** docs/superpowers/specs/2026-11-11-storage-auth-design.md

## 任务1：Redis消息仓库
- [ ] 新增message_store.py和行为测试：原生过期、分页、跨会话索引、导入保留ID、失败处理。
- [ ] 替换services/schemas/cleanup/seed中的SQL消息操作，移除Message模型；接入生命周期和健康检查。
- [ ] 运行fakeredis单测及隔离命名空间下真实Redis/WebSocket测试。

## 任务2：账号认证
- [ ] auth.py/auth_api.py/email_sender.py及测试：邮箱验证码、注册唯一性、密码哈希、会话创建撤销和错误限流。
- [ ] User增加email/password_hash，旧演示用户保留空凭证。
- [ ] HTTP/WS使用cookie身份，校验Origin，移除演示访问入口，测试伪造身份和越权。

## 任务3：登录界面
- [ ] 注册/密码登录/邮箱登录表单及邮箱发送倒计时，保留聊天界面；退出清理身份。
- [ ] API改为cookie凭据，WS移除身份query，验证401及网络失败行为。
- [ ] npm test和生产构建；浏览器验证桌面及移动布局。

## 任务4：配置迁移和联调
- [ ] 启动Mailpit并配置私有SMTP/Redis/MySQL环境；不提交任何真实凭据。
- [ ] 停止旧API写入，私有备份旧库，导入本机MySQL用户/会话及Redis有效消息，验证计数/内容摘要/绝对到期。
- [ ] 重建API/web，真实邮件注册、两类登录、双端聊天、TTL删除与历史隔离验证。
- [ ] 更新说明与交付zip，核验压缩包无凭据；本地提交全部实现，不推送。
