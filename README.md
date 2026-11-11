# 单聊原型

## 本地启动

1. 复制 `backend/.env.example` 为 `backend/.env`，保持默认 `DATABASE_URL` 指向 `127.0.0.1:3307`；需要更换宿主机端口时，同时调整 `MYSQL_PORT` 和 `DATABASE_URL`。
2. 启动 MySQL：

   ```bash
   docker compose --env-file backend/.env up -d mysql
   ```

   若尚未复制环境文件，可先直接运行 `docker compose up -d mysql`，服务默认映射至宿主机 `3307` 端口。
3. 在项目根目录启动后端：

   ```bash
   python -m backend.app.app
   ```

4. 在另一终端启动前端：

   ```bash
   cd frontend
   npm install
   npm run dev
   ```
