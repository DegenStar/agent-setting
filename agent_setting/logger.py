"""日志辅助模块"""

import datetime
import sys
from pathlib import Path

_log_path: Path | None = None


def setup_log(log_path: Path) -> None:
    """初始化日志文件（父目录必须存在）。"""
    global _log_path
    _log_path = log_path
    _log_path.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str = "") -> None:
    """将消息写入终端和日志文件（带时间戳）。"""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
        try:
            sys.stdout.write(safe_msg + "\n")
            sys.stdout.flush()
        except OSError:
            pass
    if _log_path is None:
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(str(_log_path), "a", encoding="utf-8") as f:
            if msg:
                f.write(f"[{timestamp}] {msg}\n")
            else:
                f.write("\n")
    except OSError:
        pass
