"""日志辅助模块"""

import datetime
from pathlib import Path

_log_path: Path | None = None


def setup_log(log_path: Path) -> None:
    """初始化日志文件（父目录必须存在）。"""
    global _log_path
    _log_path = log_path
    _log_path.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str = "") -> None:
    """将消息写入终端和日志文件（带时间戳）。"""
    print(msg)
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
