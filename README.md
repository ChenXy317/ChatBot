# QQ 个人号 LLM 拟人化接管服务

基于 FastAPI + SQLAlchemy (MySQL) + OneBot v11 (NapCatQQ) 的个人 QQ 号大模型接管系统。支持真人习惯模拟（1.5s 消息防抖与即时打断、换行分句、动态打字延迟、正在输入状态）、多模态图文对话与黑白极简风格 Web 管理控制台。

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
   * MySQL + SQLAlchemy 异步 ORM 存储配置、好友白名单与聊天历史。
   * Web 管理控制台支持热更新 System Prompt、模型参数、测试连通性与查看日志。

## 目录结构

```
D:\Projects\ChatBot\
├── app\
│   ├── api\               # Web REST 路由 (配置/白名单/日志/历史记录)
│   ├── core\              # 配置加载与 SQLAlchemy 异步会话
│   ├── engine\            # 核心引擎 (防抖打断 / LLM客户端 / 拟人化管道 / 思考过滤)
│   ├── gateway\           # OneBot v11 反向 WebSocket 网关
│   ├── models\            # ORM 数据表定义 (bot_config, whitelist, chat_messages)
│   └── schemas\           # Pydantic 校验模型
├── web\                   # 黑白极简 Web 控制台 (HTML / CSS / JS)
├── napcat\                # NapCat 配置示例
├── main.py                # 主服务入口
├── requirements.txt       # 依赖清单
├── .env                   # 本地数据库与服务端口配置
└── start.bat              # Windows 一键启动脚本
```

## 快速开始

### 1. 准备运行环境

* Python 3.12+ (推荐搭配 `uv`)
* MySQL 8.0 服务运行中（确认创建 `qq_chatbot` 数据库）

### 2. 配置数据库

检查根目录 `.env` 文件，确认 MySQL 账号密码：

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=qq_chatbot

SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

### 3. 启动中继后端

双击运行 `start.bat`，或在命令行中执行：

```bash
uv venv
uv pip install -r requirements.txt
python main.py
```

服务启动后访问 `http://127.0.0.1:8000` 进入管理控制台，配置你的 API Key、模型与白名单好友。

### 4. 接入 NapCatQQ

1. 启动 NapCatQQ 桌面端或 Headless 端并扫码登录个人 QQ 号。
2. 在 NapCat 的网络配置中添加反向 WebSocket 地址：
   * **URL**: `ws://127.0.0.1:8000/ws/qq`
   * **重连间隔**: `3000` ms
3. 连接成功后，控制台顶部状态点将显示为绿色在线。
