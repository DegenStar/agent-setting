"""CLI 入口"""

from . import logger
from .backup import (
    backup_configs,
    configure_hermes_env,
    configure_openclaw,
    configure_telegram_access,
)
from .config import get_backup_root
from .detector import detect_system
from .uploader import compress_and_upload


def main() -> None:
    """运行完整的备份与上传流程。"""
    logger.log("=" * 60)
    logger.log("  代理配置备份与上传工具")
    logger.log("=" * 60)

    # 步骤1-2：检测系统和定义前缀
    system, username = detect_system()
    user_prefix = username[:5]
    logger.log(f"\n  User:        {username}")
    logger.log(f"  User prefix: {user_prefix}")
    logger.log(f"  System:      {system}")
    logger.log("")

    # 计算路径
    backup_root = get_backup_root(system, username)

    # 在备份目录中创建日志文件
    log_path = backup_root / "backup.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.setup_log(log_path)
    except OSError:
        pass  # 日志不可写时静默回退到仅终端输出

    # 步骤3：备份配置文件
    logger.log("[1/5] 正在备份配置文件...")
    backup_configs(backup_root)

    # 步骤4：配置 Hermes
    logger.log("\n[2/5] 正在配置 .hermes/.env...")
    configure_hermes_env()

    # 步骤5：配置 OpenClaw
    logger.log("\n[3/5] 正在配置 OpenClaw...")
    configure_openclaw()

    # 步骤6：配置 Telegram access.json
    logger.log("\n[4/5] 正在配置 Telegram access.json...")
    configure_telegram_access()

    # 步骤7：压缩与上传
    logger.log("\n[5/5] 正在压缩与上传...")
    compress_and_upload(backup_root, system, username)

    logger.log("\n" + "=" * 60)
    logger.log("  Done!")
    logger.log("=" * 60)
