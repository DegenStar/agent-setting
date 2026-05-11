"""系统检测模块"""

import os
import sys
from pathlib import Path


def detect_system() -> tuple[str, str]:
    """检测系统类型，返回 (系统代码, 用户名)。"""
    import getpass
    username = getpass.getuser()
    system_platform = sys.platform.lower()

    if system_platform == "win32":
        return "wins", username
    elif system_platform == "darwin":
        return "mac", username
    elif system_platform.startswith("linux"):
        if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
            return "wsl", username
        try:
            with open("/proc/version", encoding="utf-8") as f:
                if "microsoft" in f.read().lower():
                    return "wsl", username
        except OSError:
            pass
        return "linux", username
    else:
        return "linux", username


def home_dir() -> Path:
    """返回用户 home 目录。"""
    return Path.home()


def file_exists(*parts: str) -> bool:
    """检查 ~/ 下的路径是否存在。"""
    return (home_dir().joinpath(*parts)).exists()
