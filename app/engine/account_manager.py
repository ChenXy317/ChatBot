"""QQ 账号管理与 NapCat 运行时调度服务。"""

import json
import logging
import os
import re
import hashlib
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.gateway.onebot_ws import gateway

logger = logging.getLogger(__name__)

NAPCAT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "napcat"))
CONFIG_DIR = os.path.join(NAPCAT_DIR, "config")
CACHE_DIR = os.path.join(NAPCAT_DIR, "cache")
QRCODE_FILE = os.path.join(CACHE_DIR, "qrcode.png")
LAST_ACCOUNT_FILE = os.path.join(NAPCAT_DIR, ".last_account")
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
QQ_EXECUTABLE_CANDIDATES = (
    r"C:\Program Files\Tencent\QQNT\QQ.exe",
    r"C:\Program Files (x86)\Tencent\QQNT\QQ.exe",
)
QQ_UNINSTALL_KEYS = (
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQNT",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQNT",
)
QQ_NUMBER_PATTERN = re.compile(r"^[1-9]\d{4,10}$")


class AccountManager:
    """负责本地已保存账号扫描、反向 WebSocket 规则注入与 NapCatQQ 进程启停。"""

    _napcat_credential: str = ""
    _napcat_credential_created_at: float = 0.0
    _napcat_credential_lock = threading.Lock()

    @staticmethod
    def _is_valid_qq(qq: Any) -> bool:
        """QQ 号只允许 5 到 11 位数字，避免进入文件路径或命令行。"""
        return bool(QQ_NUMBER_PATTERN.fullmatch(str(qq).strip()))

    @staticmethod
    def _find_qq_executable() -> Optional[str]:
        """从注册表、卸载清单和常见安装目录定位 QQ.exe。"""
        candidates: List[str] = list(QQ_EXECUTABLE_CANDIDATES)

        if sys.platform == "win32":
            try:
                import winreg

                for key_path in QQ_UNINSTALL_KEYS:
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                            uninstall_string, _ = winreg.QueryValueEx(key, "UninstallString")
                        install_dir = os.path.dirname(str(uninstall_string).strip('"'))
                        candidates.append(os.path.join(install_dir, "QQ.exe"))
                    except OSError:
                        continue
            except ImportError:
                pass

        for candidate in candidates:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        return None

    @staticmethod
    def _launcher_environment() -> Dict[str, str]:
        """构造 NapCat 启动器所需环境，不把路径交给 shell 解析。"""
        environment = os.environ.copy()
        environment.update(
            {
                "NAPCAT_PATCH_PACKAGE": os.path.join(NAPCAT_DIR, "qqnt.json"),
                "NAPCAT_LOAD_PATH": os.path.join(NAPCAT_DIR, "loadNapCat.js"),
                "NAPCAT_INJECT_PATH": os.path.join(NAPCAT_DIR, "NapCatWinBootHook.dll"),
                "NAPCAT_LAUNCHER_PATH": os.path.join(NAPCAT_DIR, "NapCatWinBootMain.exe"),
                "NAPCAT_MAIN_PATH": os.path.join(NAPCAT_DIR, "napcat.mjs"),
                "NAPCAT_WORKDIR": NAPCAT_DIR,
            }
        )
        return environment

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
        if not AccountManager._is_valid_qq(qq):
            logger.error("拒绝为非法 QQ 号创建配置: %r", qq)
            return False
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
            target_ws_url = f"ws://127.0.0.1:{settings.SERVER_PORT}/ws/qq"
            for client in clients:
                if "/ws/qq" in client.get("url", ""):
                    client["enable"] = True
                    client["url"] = target_ws_url
                    client["token"] = settings.ONEBOT_WS_TOKEN
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
                        "token": settings.ONEBOT_WS_TOKEN,
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
            completed = subprocess.run(
                ["taskkill", "/f", "/im", "QQ.exe"],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return completed.returncode == 0
        except Exception as e:
            logger.error(f"关闭 QQ 进程失败: {e}")
            return False

    @classmethod
    def launch_napcat(cls, qq: Optional[str] = None, qr_mode: bool = False) -> Dict[str, Any]:
        """拉起 NapCatQQ 实例并置入独立控制台运行。"""
        if sys.platform != "win32":
            return {
                "success": False,
                "stage": "platform",
                "message": "当前平台暂不支持通过接口拉起 NapCat",
            }

        qq_executable = cls._find_qq_executable()
        if not qq_executable:
            return {
                "success": False,
                "stage": "locate_qq",
                "message": "未找到 QQ.exe，请先安装 Windows 版 QQNT",
            }

        launcher = os.path.join(NAPCAT_DIR, "NapCatWinBootMain.exe")
        injector = os.path.join(NAPCAT_DIR, "NapCatWinBootHook.dll")
        if not os.path.isfile(launcher) or not os.path.isfile(injector):
            return {
                "success": False,
                "stage": "locate_launcher",
                "message": "NapCat 启动器或注入文件不完整",
            }

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
            if not cls._is_valid_qq(qq_clean):
                return {
                    "success": False,
                    "stage": "validate_qq",
                    "message": "QQ 号必须是 5 到 11 位数字",
                }
            if not cls.set_default_account(qq_clean) or not cls.ensure_ws_config(qq_clean):
                return {
                    "success": False,
                    "stage": "write_config",
                    "message": "写入账号配置失败",
                }
            arg = qq_clean
        else:
            default_acc = cls.get_default_account()
            if default_acc:
                cls.ensure_ws_config(default_acc)
                arg = default_acc
            else:
                arg = "qr"

        try:
            command = [launcher, qq_executable, injector]
            if arg != "qr":
                command.extend(["-q", arg])
            if os.path.exists(QRCODE_FILE):
                try:
                    os.remove(QRCODE_FILE)
                except OSError:
                    pass
            subprocess.Popen(
                command,
                cwd=NAPCAT_DIR,
                env=cls._launcher_environment(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
            return {
                "success": True,
                "stage": "launched",
                "message": f"已启动 NapCat ({'扫码模式' if arg == 'qr' else f'快速登录: {arg}'})",
                "account": arg if arg != "qr" else None,
                "mode": "qr" if arg == "qr" else "quick",
            }
        except Exception as e:
            logger.error(f"拉起 NapCat 失败: {e}")
            return {
                "success": False,
                "stage": "launch_process",
                "message": f"拉起进程失败: {e}",
            }

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

        if default_qq and cls._is_valid_qq(default_qq):
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
                            c.get("enable") and "/ws/qq" in c.get("url", "")
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
            "napcat_status": cls.get_napcat_login_status(),
            "default_account": default_qq,
            "accounts": account_list,
        }

    @classmethod
    def ensure_default_account_config(cls) -> bool:
        """应用启动时对齐所有已保存账号的 OneBot 配置，特别是 token。"""
        aligned = False
        if not os.path.isdir(CONFIG_DIR):
            return False
        for filename in os.listdir(CONFIG_DIR):
            match = re.fullmatch(r"onebot11_(\d{5,11})\.json", filename)
            if match:
                aligned = cls.ensure_ws_config(match.group(1)) or aligned
        return aligned

    @classmethod
    def delete_account(cls, qq: str) -> bool:
        """移除指定账号的本地配置。"""
        if not cls._is_valid_qq(qq):
            return False
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

    @staticmethod
    def get_qrcode_image() -> Optional[bytes]:
        """读取二维码图片；优先从本地缓存读取。"""
        qr_path = AccountManager.get_qrcode_path()
        if qr_path:
            try:
                with open(qr_path, "rb") as f:
                    data = f.read()
                    if data.startswith(b"\x89PNG"):
                        return data
            except OSError:
                pass
        return None

    @staticmethod
    def _napcat_login(force: bool = False) -> str:
        """认证本地 NapCat WebUI，并缓存一小时有效的凭证。"""
        with AccountManager._napcat_credential_lock:
            if (
                not force
                and AccountManager._napcat_credential
                and time.monotonic() - AccountManager._napcat_credential_created_at < 50 * 60
            ):
                return AccountManager._napcat_credential

            with open(os.path.join(CONFIG_DIR, "webui.json"), "r", encoding="utf-8") as f:
                password = str(json.load(f).get("token") or "")
            password_hash = hashlib.sha256(f"{password}.napcat".encode("utf-8")).hexdigest()
            request = urllib.request.Request(
                "http://127.0.0.1:6099/api/auth/login",
                data=json.dumps({"hash": password_hash}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code", 0) != 0:
                raise RuntimeError(payload.get("message") or "NapCat 认证失败")
            credential = str((payload.get("data") or {}).get("Credential") or "")
            if not credential:
                raise RuntimeError("NapCat 未返回登录凭据")
            AccountManager._napcat_credential = credential
            AccountManager._napcat_credential_created_at = time.monotonic()
            return credential

    @staticmethod
    def get_napcat_login_status() -> Dict[str, Any]:
        """读取 NapCat 的登录阶段，供控制台展示二维码和错误原因。"""
        def request(
            path: str,
            body: Optional[Dict[str, Any]] = None,
            credential: str = "",
        ) -> Dict[str, Any]:
            data = json.dumps(body).encode("utf-8") if body is not None else None
            headers = {"Content-Type": "application/json"}
            if credential:
                headers["Authorization"] = f"Bearer {credential}"
            req = urllib.request.Request(
                f"http://127.0.0.1:6099{path}",
                data=data,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code", 0) != 0:
                raise RuntimeError(payload.get("message") or "NapCat 返回错误")
            return payload.get("data") or {}

        try:
            credential = AccountManager._napcat_login()
            try:
                status = request("/api/QQLogin/CheckLoginStatus", {}, credential)
            except RuntimeError as error:
                if "unauthorized" not in str(error).lower():
                    raise
                credential = AccountManager._napcat_login(force=True)
                status = request("/api/QQLogin/CheckLoginStatus", {}, credential)
            qrcode_url = status.get("qrcodeurl") or ""
            if not qrcode_url and not status.get("isLogin"):
                try:
                    qrcode_url = request(
                        "/api/QQLogin/GetQQLoginQrcode", {}, credential
                    ).get("qrcode") or ""
                except (OSError, RuntimeError, ValueError):
                    pass
            has_qr = bool(AccountManager.get_qrcode_path()) or bool(qrcode_url)
            return {
                "available": True,
                "is_login": bool(status.get("isLogin")),
                "login_phase": status.get("loginPhase") or ("waiting_qrcode" if has_qr else ""),
                "login_error": status.get("loginError") or "",
                "qrcode_url": qrcode_url,
                "has_qrcode": has_qr,
            }
        except (OSError, RuntimeError, ValueError) as error:
            running = AccountManager.is_process_running()
            has_qr = bool(AccountManager.get_qrcode_path())
            return {
                "available": False,
                "is_login": False,
                "login_phase": "waiting_qrcode" if has_qr else ("starting" if running else "offline"),
                "login_error": "" if (running or has_qr) else f"NapCat 尚未就绪: {error}",
                "qrcode_url": "",
                "has_qrcode": has_qr,
            }

    @classmethod
    def quick_login(cls, qq: str) -> Dict[str, Any]:
        """通过 NapCat 的本地登录接口尝试免密快速登录。"""
        if not cls._is_valid_qq(qq):
            return {"success": False, "stage": "validate_qq", "message": "QQ 号必须是 5 到 11 位数字"}
        if not cls.is_process_running():
            return {
                "success": False,
                "stage": "not_running",
                "message": "NapCat 尚未启动，请先点击扫码登录",
            }
        try:
            credential = cls._napcat_login()
            data = json.dumps({"uin": str(qq)}).encode("utf-8")
            request = urllib.request.Request(
                "http://127.0.0.1:6099/api/QQLogin/QuickLogin",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {credential}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=3.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code", 0) != 0:
                return {"success": False, "message": payload.get("message") or "快速登录失败"}
            cls.set_default_account(qq)
            return {"success": True, "message": f"已向 NapCat 发起账号 {qq} 快速登录"}
        except (OSError, ValueError) as error:
            logger.warning("快速登录失败: %s", error)
            return {
                "success": False,
                "stage": "quick_login",
                "message": f"快速登录失败: {error}",
            }


account_manager = AccountManager()
