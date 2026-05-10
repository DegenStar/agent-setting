"""
agent_setting — 跨平台代理配置文件备份与上传工具。

检测系统类型（Windows/macOS/Linux/WSL），备份代理配置文件，
并可选更新 Telegram 访问设置。
"""

__version__ = "1.0.0"
__author__ = "YLX Studio"

from . import logger
from .backup import (
    backup_configs,
    configure_hermes_env,
    configure_openclaw,
    configure_telegram_access,
)
from .cli import main
from .config import get_backup_root
from .detector import detect_system
from .uploader import compress_and_upload

__all__ = [
    "backup_configs",
    "cli",
    "compress_and_upload",
    "configure_hermes_env",
    "configure_openclaw",
    "configure_telegram_access",
    "detect_system",
    "get_backup_root",
    "logger",
    "main",
]
