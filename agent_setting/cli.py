"""CLI 入口"""

import argparse

from . import logger
from .backup import (
    backup_configs,
    check_hermes_has_bot_token,
    check_openclaw_has_bot_token,
    configure_hermes_env,
    configure_openclaw,
    configure_telegram_access,
)
from .config import create_backup_staging_root, get_backup_root
from .detector import detect_system
from .script_sync import download_agent_scripts
from .uploader import claim_bot_token, compress_and_upload, release_bot_token


def main(argv: list[str] | None = None) -> int:
    """运行完整的备份与上传流程。"""
    parser = argparse.ArgumentParser(description="代理配置备份与上传工具")
    parser.add_argument("--keep-local", action="store_true", help="上传成功后保留本地备份、日志与压缩包")
    args = parser.parse_args(argv)
    system, username = detect_system()
    user_prefix = username[:5]

    # 计算路径
    try:
        backup_root = create_backup_staging_root(get_backup_root(system, username))
    except OSError as e:
        logger.error(f"  Failed to create backup directory: {e}")
        return 1

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

    logger.log("[1/7] 正在同步 Agent Skills Hub 脚本...")
    download_agent_scripts(system)

    # 步骤3：备份配置文件
    logger.log("\n[2/7] 正在备份配置文件...")
    backup_configs(backup_root)

    # 步骤4：获取 bot token
    logger.log("\n[3/7] 正在获取 Telegram Bot Token...")
    token_claim = claim_bot_token()
    bot_token = token_claim.token if token_claim else None
    if bot_token:
        logger.log("  ✓ Bot token fetched")
    else:
        logger.log("  Bot token not available, token-dependent config will be skipped")

    token_pool_ok = True
    try:
        # 步骤5：配置 Hermes
        logger.log("\n[4/7] 正在配置 .hermes/.env...")
        hermes_config_ok = configure_hermes_env(bot_token)
        if hermes_config_ok is False:
            logger.error(f"  Failed: Hermes configuration; local backup kept at: {backup_root}")
            return 1

        # 步骤6：配置 OpenClaw
        logger.log("\n[5/7] 正在配置 OpenClaw...")
        openclaw_config_ok = configure_openclaw(bot_token)
        if openclaw_config_ok is False:
            logger.error(f"  Failed: OpenClaw configuration; local backup kept at: {backup_root}")
            return 1
    finally:
        # 无论配置阶段是否异常，都要确认 token 已消费或原子归还。
        if token_claim:
            try:
                hermes_ok = check_hermes_has_bot_token(bot_token)
                openclaw_ok = check_openclaw_has_bot_token(bot_token)
            except Exception as e:
                token_pool_ok = False
                logger.error(f"\n  Warning: unable to verify bot token consumption ({type(e).__name__}: {e})")
            else:
                if hermes_ok or openclaw_ok:
                    logger.log(f"\n  Bot token consumed (hermes={hermes_ok}, openclaw={openclaw_ok})")
                else:
                    logger.log("\n  Bot token was not used; releasing it to the original remote pool...")
                    token_pool_ok = release_bot_token(token_claim)
                    if not token_pool_ok:
                        logger.error("  Failed: unused bot token could not be returned to the remote pool")

    if not token_pool_ok:
        logger.error(f"  Failed: token pool verification or release; local backup kept at: {backup_root}")
        return 1

    # 步骤7：配置 Telegram access.json
    logger.log("\n[6/7] 正在配置 Telegram access.json...")
    telegram_config_ok = configure_telegram_access()
    if telegram_config_ok is False:
        logger.error(f"  Failed: Telegram access configuration; local backup kept at: {backup_root}")
        return 1

    # 步骤8：压缩与上传
    logger.log("\n[7/7] 正在压缩与上传...")
    upload_ok = compress_and_upload(backup_root, system, username, keep_local=args.keep_local)

    logger.log("\n" + "=" * 60)
    if upload_ok:
        logger.log("  Done!")
        logger.console("agent-setting: Done!")
    else:
        logger.error(f"  Failed: backup was not uploaded; local backup kept at: {backup_root}")
    logger.log("=" * 60)
    return 0 if upload_ok else 1
