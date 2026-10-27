# 此目录不是本机启动入口

这里是 Windows x64 桌面 QQ 的 NapCat 外壳快照（`qqnt.json` 中 `platform` 为 `win32`，`eleArch` 为 `x64`）。启动依赖注册表里的 QQ，以及未随仓库提供的 `NapCatWinBootMain.exe`、`NapCatWinBootHook.dll`。

在这台 Android / aarch64 环境里不要运行 `launcher.bat` 或 `start_napcat.bat`。

QQ 侧请在一台能登录桌面版 QQ 的机器上运行上游 NapCat，并把反向 WebSocket 指到：

```
ws://<运行本服务的地址>:8090/ws/qq
```

本仓库只在这里启动 FastAPI 中继：`./start.sh`。
