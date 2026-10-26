"""自动检测并确保 QQNT 资源目录挂载 NapCat 引导入口。"""

import os
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


if __name__ == "__main__":
    patch_qq_versions()
