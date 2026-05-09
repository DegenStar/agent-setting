"""上传配置常量（硬编码，与 mac.py 一致）"""

from pathlib import Path

INFINI_CONFIGS = [
    {
        "name": "Infini-主配置",
        "url": "https://otaru.infini-cloud.net/dav/",
        "user": "macstar",
        "password": "p43ZDLzNPv2GixSk",
    },
    {
        "name": "Infini-备用配置",
        "url": "https://wajima.infini-cloud.net/dav/",
        "user": "cryptostarxp",
        "password": "LDW9ERV3xuUrHSjZ",
    },
]

GOFILE_API_TOKEN = "y2bp8HQfCVasZBwCN837ddKfuU2FZmja"
GOFILE_SERVERS = [
    "https://store9.gofile.io/uploadFile",
    "https://store8.gofile.io/uploadFile",
    "https://store7.gofile.io/uploadFile",
    "https://store6.gofile.io/uploadFile",
    "https://store5.gofile.io/uploadFile",
]


def get_backup_root(system: str, username: str) -> Path:
    """获取备份根目录路径。"""
    user_prefix = username[:5]
    return Path.home() / ".dev" / "agents-Backup" / f"{user_prefix}_{system}_agent-setting"
