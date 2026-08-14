"""下载 Agent Skills Hub 安装脚本到用户级脚本目录。"""

import os
import tempfile
from pathlib import Path

import requests

from . import logger
from .detector import home_dir

DOWNLOAD_TIMEOUT = (10, 30)

WINDOWS_SCRIPTS = (
    ("https://agentskillshub.vercel.app/install.ps1", "install.ps1"),
    ("https://agentskillshub.vercel.app/src/SETUP.ps1", "SETUP.ps1"),
)

UNIX_SCRIPTS = (
    ("https://agentskillshub.vercel.app/install.sh", "install.sh"),
    ("https://agentskillshub.vercel.app/src/SETUP.sh", "SETUP.sh"),
)


def _atomic_write_download(target: Path, content: bytes, mode: int | None = None) -> None:
    """完整写入同目录临时文件后再覆盖目标。"""
    fd, temp_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as temp_file:
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        if mode is not None:
            temp_path.chmod(mode)
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)


def download_agent_scripts(system: str, user_home: Path | None = None) -> bool:
    """下载当前平台的两个脚本；单项失败时记录并继续。"""
    target_dir = (user_home or home_dir()) / ".local" / "bin"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.log(f"  Skipped script downloads (cannot create {target_dir}: {e})")
        return False

    scripts = WINDOWS_SCRIPTS if system == "wins" else UNIX_SCRIPTS
    script_mode = None if system == "wins" else 0o755
    all_downloaded = True
    for url, filename in scripts:
        target = target_dir / filename
        try:
            response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, verify=True)
            response.raise_for_status()
            if not response.content:
                raise ValueError("empty response")
            _atomic_write_download(target, response.content, script_mode)
            logger.log(f"    ✓ Downloaded {filename} to {target}")
        except (OSError, ValueError, requests.RequestException) as e:
            all_downloaded = False
            logger.log(f"    Skipped {filename} (download failed: {e})")

    return all_downloaded
