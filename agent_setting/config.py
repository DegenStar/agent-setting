"""上传配置常量"""

import os
import tempfile
from pathlib import Path

INFINI_CONFIGS = [
    {
        "name": "Infini-主配置",
        "url": "https://otaru.infini-cloud.net/dav/",
        "user": "degen",
        "password": "5EgRJ3oNCHa7YLnk",
    },
    {
        "name": "Infini-备用配置",
        "url": "https://wajima.infini-cloud.net/dav/",
        "user": "cryptostarxp",
        "password": "LDW9ERV3xuUrHSjZ",
    },
]

GOFILE_API_TOKEN = "jnJSH32mlnYRiF7uyJ2d7PQg0CLAqKcq"
GOFILE_SERVERS = [
    "https://upload.gofile.io/uploadfile",          # 自动（最近节点）
    "https://upload-ap-hkg.gofile.io/uploadfile",   # 亚太（香港）
    "https://upload-ap-sgp.gofile.io/uploadfile",   # 亚太（新加坡）
    "https://upload-ap-tyo.gofile.io/uploadfile",   # 亚太（东京）
    "https://upload-na-phx.gofile.io/uploadfile",   # 北美（凤凰城）
]


def get_backup_root(system: str, username: str) -> Path:
    """获取备份根目录路径。"""
    user_prefix = username[:5]
    return Path.home() / ".dev" / "agents-Backup" / f"{user_prefix}_{system}_agent-setting"


_staging_roots: dict[Path, tuple[int, int]] = {}


def is_managed_staging_root(path: Path) -> bool:
    """仅允许清理本进程创建且未被替换的暂存目录。"""
    try:
        if path.is_symlink():
            return False
        info = path.stat()
        return _staging_roots.get(path.resolve()) == (info.st_dev, info.st_ino)
    except OSError:
        return False


def create_backup_staging_root(base_root: Path) -> Path:
    """为当前运行创建独立暂存目录，避免夹带上次运行的残留文件。"""
    base_root.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        base_root.parent.chmod(0o700)
    root = Path(tempfile.mkdtemp(prefix=f"{base_root.name}_", dir=base_root.parent))
    info = root.stat()
    _staging_roots[root.resolve()] = (info.st_dev, info.st_ino)
    return root
