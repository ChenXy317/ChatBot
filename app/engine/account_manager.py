"""QQ 账号管理与 NapCat 运行时调度服务。"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.gateway.onebot_ws import gateway

logger = logging.getLogger(__name__)

NAPCAT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "napcat"))
CONFIG_DIR = os.path.join(NAPCAT_DIR, "config")
CACHE_DIR = os.path.join(NAPCAT_DIR, "cache")
QRCODE_FILE = os.path.join(CACHE_DIR, "qrcode.png")
LAST_ACCOUNT_FILE = os.path.join(NAPCAT_DIR, ".last_account")
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
START_NAPCAT_BAT = os.path.join(ROOT_DIR, "start_napcat.bat")


class AccountManager:
    """负责本地已保存账号扫描、反向 WebSocket 规则注入与 NapCatQQ 进程启停。"""

    @staticmethod
    def get_default_account() -> Optional[str]:
        """获取本地预设的默认启动 QQ 号。"""
        if os.path.exists(LAST_ACCOUNT_FILE):
            try:
                with open(LAST_ACCOUNT_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception as e:
                logger.error(f"读取默认账号文件失败: {e}")
        return None

    @staticmethod
    def set_default_account(qq: str) -> bool:
        """设置默认启动 QQ 号。"""
        try:
            with open(LAST_ACCOUNT_FILE, "w", encoding="utf-8") as f:
                f.write(str(qq).strip())
            return True
        except Exception as e:
            logger.error(f"写入默认账号文件失败: {e}")
            return False

    @staticmethod
    def ensure_ws_config(qq: str) -> bool:
        """确保指定账号的 OneBot 配置文件具备指向本系统的反向 WebSocket 连接。"""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            target_file = os.path.join(CONFIG_DIR, f"onebot11_{qq}.json")
            template_file = os.path.join(CONFIG_DIR, "onebot11.json")

            cfg: Dict[str, Any] = {}
            if os.path.exists(target_file):
                try:
                    with open(target_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    cfg = {}

            if not cfg and os.path.exists(template_file):
                try:
                    with open(template_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    cfg = {}

            network = cfg.setdefault("network", {})
            clients = network.setdefault("websocketClients", [])

            has_client = False
            target_ws_url = "ws://127.0.0.1:8090/ws/qq"
            for client in clients:
                if "8090/ws/qq" in client.get("url", ""):
                    client["enable"] = True
                    client["url"] = target_ws_url
                    has_client = True
                    break

            if not has_client:
                clients.append(
                    {
                        "enable": True,
                        "name": "ChatBot-Backend",
                        "url": target_ws_url,
                        "reportSelfMessage": False,
                        "reconnectInterval": 3000,
                        "messagePostFormat": "array",
                        "token": "",
                        "debug": False,
                        "heartInterval": 30000,
                        "verifyCertificate": True,
                    }
                )

            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            logger.error(f"对齐账号 [{qq}] OneBot 反向配置失败: {e}")
            return False

    @staticmethod
    def is_process_running() -> bool:
        """检查当前系统中是否存在 QQ.exe 进程。"""
        if sys.platform != "win32":
            return False
        try:
            res = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq QQ.exe"],
                capture_output=True,
                text=True,
                check=False,
            )
            return "qq.exe" in (res.stdout or "").lower()
        except Exception as e:
            logger.error(f"探测 QQ 进程状态异常: {e}")
            return False

    @staticmethod
    def stop_napcat() -> bool:
        """停止当前运行的 QQ/NapCat 进程。"""
        if sys.platform != "win32":
            return False
        try:
            subprocess.run(["taskkill", "/f", "/im", "QQ.exe"], capture_output=True, check=False)
            return True
        except Exception as e:
            logger.error(f"关闭 QQ 进程失败: {e}")
            return False

    @classmethod
    def launch_napcat(cls, qq: Optional[str] = None, qr_mode: bool = False) -> Dict[str, Any]:
        """拉起 NapCatQQ 实例并置入独立控制台运行。"""
        if sys.platform != "win32":
            return {"success": False, "message": "当前平台暂不支持通过接口拉起 NapCat"}

        # 先关闭可能存在的旧进程
        cls.stop_napcat()
        time.sleep(0.8)

        # 挂载入口补丁
        try:
            from napcat.patch_loader import patch_qq_versions
            patch_qq_versions()
        except Exception as e:
            logger.warning(f"对齐 QQNT 补丁异常: {e}")

        # 启动模式解析
        arg = ""
        if qr_mode:
            arg = "qr"
            if os.path.exists(QRCODE_FILE):
                try:
                    os.remove(QRCODE_FILE)
                except Exception:
                    pass
        elif qq:
            qq_clean = str(qq).strip()
            cls.set_default_account(qq_clean)
            cls.ensure_ws_config(qq_clean)
            arg = qq_clean
        else:
            default_acc = cls.get_default_account()
            if default_acc:
                cls.ensure_ws_config(default_acc)
                arg = default_acc
            else:
                arg = "qr"

        try:
            cmd = f'start "NapCatQQ" cmd /c "call \"{START_NAPCAT_BAT}\" {arg}"'
            subprocess.Popen(cmd, shell=True, cwd=ROOT_DIR)
            return {
                "success": True,
                "message": f"已启动 NapCat ({'扫码模式' if arg == 'qr' else f'快速登录: {arg}'})",
                "account": arg if arg != "qr" else None,
                "mode": "qr" if arg == "qr" else "quick",
            }
        except Exception as e:
            logger.error(f"拉起 NapCat 失败: {e}")
            return {"success": False, "message": f"拉起进程失败: {e}"}

    @classmethod
    def list_accounts(cls) -> Dict[str, Any]:
        """获取所有已记录账号及当前运行时状态。"""
        default_qq = cls.get_default_account()
        is_running = cls.is_process_running()
        current_online = gateway.current_qq if gateway.is_connected else None

        found_qqs = set()
        if os.path.exists(CONFIG_DIR):
            for f in os.listdir(CONFIG_DIR):
                m1 = re.match(r"onebot11_(\d+)\.json$", f)
                if m1:
                    found_qqs.add(m1.group(1))
                m2 = re.match(r"napcat_(\d+)\.json$", f)
                if m2:
                    found_qqs.add(m2.group(1))

        if default_qq:
            found_qqs.add(default_qq)
        if current_online:
            found_qqs.add(current_online)

        account_list: List[Dict[str, Any]] = []
        for q in sorted(found_qqs):
            cfg_path = os.path.join(CONFIG_DIR, f"onebot11_{q}.json")
            has_cfg = os.path.exists(cfg_path)
            last_active = ""
            has_ws = False
            if has_cfg:
                try:
                    mt = os.path.getmtime(cfg_path)
                    last_active = datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S")
                    with open(cfg_path, "r", encoding="utf-8") as fp:
                        c_data = json.load(fp)
                        ws_clients = c_data.get("network", {}).get("websocketClients", [])
                        has_ws = any(
                            c.get("enable") and "8090/ws/qq" in c.get("url", "")
                            for c in ws_clients
                        )
                except Exception:
                    pass

            account_list.append(
                {
                    "qq": q,
                    "is_online": q == current_online,
                    "is_default": q == default_qq,
                    "has_ws_config": has_ws,
                    "last_active": last_active,
                }
            )

        return {
            "online_qq": current_online,
            "online_nickname": gateway.current_nickname if gateway.is_connected else None,
            "is_connected": gateway.is_connected,
            "is_process_running": is_running,
            "default_account": default_qq,
            "accounts": account_list,
        }

    @classmethod
    def delete_account(cls, qq: str) -> bool:
        """移除指定账号的本地配置。"""
        try:
            targets = [
                os.path.join(CONFIG_DIR, f"onebot11_{qq}.json"),
                os.path.join(CONFIG_DIR, f"napcat_{qq}.json"),
                os.path.join(CONFIG_DIR, f"napcat_protocol_{qq}.json"),
            ]
            for t in targets:
                if os.path.exists(t):
                    os.remove(t)
            if cls.get_default_account() == str(qq).strip():
                if os.path.exists(LAST_ACCOUNT_FILE):
                    os.remove(LAST_ACCOUNT_FILE)
            return True
        except Exception as e:
            logger.error(f"删除账号 [{qq}] 失败: {e}")
            return False

    @staticmethod
    def get_qrcode_path() -> Optional[str]:
        """获取当前有效的扫码二维码图片路径。"""
        if os.path.exists(QRCODE_FILE) and os.path.getsize(QRCODE_FILE) > 0:
            return QRCODE_FILE
        return None


account_manager = AccountManager()
