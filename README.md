# QQ 个人号 LLM 拟人化接管服务

基于 FastAPI + SQLAlchemy (MySQL/MariaDB) + OneBot v11 的个人 QQ 号大模型接管系统。支持真人习惯模拟（1.5s 消息防抖与即时打断、换行分句、动态打字延迟、正在输入状态）、多模态图文对话与黑白极简风格 Web 管理控制台。

## 功能架构

1. **消息缓冲与打断机制**：
   * 收到好友私聊消息后进入 1.5 秒缓冲计时。
   * 好友在 1.5 秒内连续发送新消息时重置计时并将消息合并。
   * 若大模型已在准备或生成回复中，一旦收到新消息立即取消并丢弃当前任务，合并最新内容后重新触发。
2. **拟人化表现层**：
   * 自动过滤 DeepSeek 等推理模型的 `<think>` 思考块。
   * 根据换行符拆解为短句依次发送，并向 QQ 推送“正在输入中...”状态。
   * 根据回复字数动态计算打字耗时（模拟真人按键速度）。
3. **多模态与时间戳**：
   * 兼容 OpenAI Chat 规范的多模态接口，支持接收并解析 QQ 图片。
   * 每轮上下文注入精确时间戳（如 `[2026-10-26 21:15:30]`）。
4. **数据持久化与管理**：
   * MySQL/MariaDB + SQLAlchemy 异步 ORM 存储配置、好友白名单与聊天历史。
   * Web 管理控制台支持热更新 System Prompt、模型参数、测试连通性与查看日志。

## 目录结构

```
ChatBot/
├── app/                   # 中继后端
├── web/                   # 黑白极简 Web 控制台
├── napcat/                # Windows 版 NapCat 快照，不是本机启动入口
├── main.py
├── requirements.txt
├── .env                   # 本地数据库与服务端口，不入库
├── start.sh               # 本机（Android + Termux MariaDB）启动脚本
└── start.bat              # Windows 启动脚本
```

## 在本机启动

这台机器是 Android 上的 Ubuntu aarch64，数据库是已经装好的 Termux MariaDB 12.3（数据目录 `/data/data/com.termux/files/usr/var/lib/mysql`）。本服务使用单独的库 `qq_chatbot`，`root` 通过 `127.0.0.1:3306` 登录，密码为空。

```bash
chmod +x start.sh
./start.sh
```

脚本会在 3306 没人听的时候拉起 MariaDB，创建 `qq_chatbot`，用 `uv` 安装依赖，然后启动 `http://127.0.0.1:8090`。

仓库里的 `napcat/` 是 Windows x64 QQ 注入壳，不要在这里执行 `start_napcat.bat`。QQ 协议端放到能登录桌面版 QQ 的机器上，反向 WebSocket 填：

```
ws://<这台机器的地址>:8090/ws/qq
```

## Windows 快速开始

### 1. 准备运行环境

* Python 3.12+（推荐搭配 `uv`）
* MySQL 8.0 或 MariaDB 已在运行，并创建 `qq_chatbot` 数据库

### 2. 配置数据库

检查根目录 `.env`：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=qq_chatbot

SERVER_HOST=0.0.0.0
SERVER_PORT=8090
```

### 3. 启动中继后端

双击 `start.bat`，或：

```bash
uv venv
uv pip install -r requirements.txt
python main.py
```

打开 `http://127.0.0.1:8090`，配置 API Key、模型与白名单好友。

### 4. 接入 NapCatQQ

1. 在 Windows 上启动 NapCatQQ 并扫码登录个人 QQ。
2. 添加反向 WebSocket：
   * **URL**: `ws://127.0.0.1:8090/ws/qq`
   * **重连间隔**: `3000` ms
3. 连接成功后，控制台顶部状态点显示为绿色。
