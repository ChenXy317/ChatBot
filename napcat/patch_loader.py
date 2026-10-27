"""自动检测并确保 QQNT 资源目录挂载 NapCat 引导入口，并记录最近登录账号与 QQ 路径。"""

import glob
import os
import re
import winreg


def patch_qq_versions():
    """遍历 QQ 版本目录，确保放置引导文件 loadNapCat.js。"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
        )
        uninstall_str, _ = winreg.QueryValueEx(key, "UninstallString")
        qq_dir = os.path.dirname(uninstall_str.strip('"'))
        versions_dir = os.path.join(qq_dir, "versions")

        current_dir = os.path.abspath(os.path.dirname(__file__))
        napcat_mjs = os.path.join(current_dir, "napcat.mjs").replace("\\", "/")

        if os.path.exists(versions_dir):
            for v_name in os.listdir(versions_dir):
                app_dir = os.path.join(versions_dir, v_name, "resources", "app")
                if os.path.exists(app_dir):
                    loader_path = os.path.join(app_dir, "loadNapCat.js")
                    content = (
                        "const path = require('path');\n"
                        "const { pathToFileURL } = require('url');\n"
                        f"const mainPath = process.env.NAPCAT_MAIN_PATH || '{napcat_mjs}';\n"
                        "(async () => {\n"
                        "  await import(pathToFileURL(mainPath).href);\n"
                        "})();\n"
                    )
                    with open(loader_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"已自动对齐 QQ 入口引导: {loader_path}")
    except Exception as e:
        print(f"检查 QQ 目录异常: {e}")


def record_latest_account():
    """检测最近登录的 QQ 账号，供免密快速登录使用（仅在未设置时填充）。"""
    try:
        current_dir = os.path.abspath(os.path.dirname(__file__))
        last_account_file = os.path.join(current_dir, ".last_account")
        if os.path.exists(last_account_file):
            with open(last_account_file, "r", encoding="utf-8") as f:
                if f.read().strip():
                    return
        config_dir = os.path.join(current_dir, "config")
        files = glob.glob(os.path.join(config_dir, "onebot11_*.json"))
        if files:
            files.sort(key=os.path.getmtime, reverse=True)
            m = re.search(r"onebot11_(\d+)\.json", os.path.basename(files[0]))
            if m:
                latest_qq = m.group(1)
                with open(last_account_file, "w", encoding="utf-8") as f:
                    f.write(latest_qq.strip())
                print(f"检测到最近登录账号: {latest_qq}")
    except Exception as e:
        print(f"记录账号异常: {e}")


def record_qq_path():
    """检测 QQ.exe 绝对路径并写入 .qq_path，供启动脚本直接定位。"""
    try:
        current_dir = os.path.abspath(os.path.dirname(__file__))
        qq_path_file = os.path.join(current_dir, ".qq_path")

        candidates = []
        for reg_key in (
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQNT",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QQNT",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key) as key:
                    uninstall_str, _ = winreg.QueryValueEx(key, "UninstallString")
                    qq_dir = os.path.dirname(str(uninstall_str).strip('"'))
                    candidates.append(os.path.join(qq_dir, "QQ.exe"))
            except OSError:
                continue

        candidates.extend([
            r"D:\工具2\QQ\QQ.exe",
            os.path.expandvars(r"%ProgramFiles%\Tencent\QQNT\QQ.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Tencent\QQNT\QQ.exe"),
            os.path.expandvars(r"%LocalAppData%\Programs\Tencent\QQNT\QQ.exe"),
        ])

        for c in candidates:
            if os.path.isfile(c):
                with open(qq_path_file, "w", encoding="utf-8") as f:
                    f.write(os.path.abspath(c))
                print(f"已锁定 QQNT 可执行文件路径: {c}")
                return
    except Exception as e:
        print(f"检测 QQ 路径异常: {e}")


if __name__ == "__main__":
    patch_qq_versions()
    record_latest_account()
    record_qq_path()
