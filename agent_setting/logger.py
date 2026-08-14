"""日志辅助模块"""

import datetime
import sys
from pathlib import Path

_log_path: Path | None = None


def setup_log(log_path: Path) -> None:
    """初始化日志文件，并在文件名后追加时间戳后缀。"""
    global _log_path
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    _log_path = log_path.with_name(f"{log_path.stem}-{timestamp}{log_path.suffix}")
    _log_path.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str = "") -> None:
    """将消息写入日志文件（带时间戳）。"""
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


def console(msg: str) -> None:
    """将需要用户立即看到的状态写到标准错误。"""
    try:
        sys.stderr.write(f"{msg}\n")
        sys.stderr.flush()
    except (OSError, UnicodeError):
        pass


def error(msg: str) -> None:
    """记录错误并同步显示到终端。"""
    log(msg)
    console(msg)
