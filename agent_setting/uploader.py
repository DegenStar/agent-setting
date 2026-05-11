"""上传模块（Infini Cloud + GoFile 回退）"""

import datetime
import os
import shutil
import tarfile
import time
from pathlib import Path

import requests
import urllib3
from requests.auth import HTTPBasicAuth

from . import config as cfg
from . import logger

# 禁用 SSL 警告（因为某些云存储服务可能使用自签名证书）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _create_remote_directory(session, url: str, remote_dir: str, auth) -> bool:
    """通过 WebDAV MKCOL 创建远程目录。"""
    if not remote_dir or remote_dir == ".":
        return True
    dir_path = f"{url.rstrip('/')}/{remote_dir.lstrip('/')}"
    try:
        resp = session.request("MKCOL", dir_path, auth=auth, timeout=(8, 8))
        if resp.status_code in (201, 204, 405):
            return True
        if resp.status_code == 409:
            parent = os.path.dirname(remote_dir)
            if parent and parent != ".":
                if _create_remote_directory(session, url, parent, auth):
                    resp = session.request("MKCOL", dir_path, auth=auth, timeout=(8, 8))
                    return resp.status_code in (201, 204, 405)
        return False
    except Exception:
        return False


def _upload_infini(session, file_path: str, remote_path: str, auth, config_name: str) -> bool:
    """通过 WebDAV PUT 上传单个文件到 Infini Cloud。"""
    file_size = os.path.getsize(file_path)
    connect_timeout = 10
    read_timeout = max(30, int(file_size / 1024 / 1024 * 5)) if file_size > 1024 * 1024 else 30

    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                resp = session.put(
                    remote_path,
                    data=f,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(file_size),
                    },
                    auth=auth,
                    timeout=(connect_timeout, read_timeout),
                )
            if resp.status_code in (201, 204):
                logger.log(f"    ✓ [{config_name}] upload successful")
                return True
            elif resp.status_code == 401:
                logger.log(f"    ✗ [{config_name}] authentication failed")
                return False
            elif resp.status_code == 403:
                logger.log(f"    ✗ [{config_name}] permission denied")
                return False
            else:
                logger.log(f"    [{config_name}] attempt {attempt + 1} failed (HTTP {resp.status_code}), retrying...")
        except requests.exceptions.Timeout:
            logger.log(f"    [{config_name}] attempt {attempt + 1} timed out, retrying...")
        except requests.exceptions.ConnectionError:
            logger.log(f"    [{config_name}] attempt {attempt + 1} connection error, retrying...")
        except Exception as e:
            logger.log(f"    [{config_name}] attempt {attempt + 1} error: {e}")
            return False
        time.sleep(5)
    return False


def _upload_gofile(file_path: str) -> bool:
    """上传单个文件到 GoFile（备用方案）。"""
    filename = os.path.basename(file_path)
    logger.log("    Trying GoFile fallback...")

    server_count = len(cfg.GOFILE_SERVERS)
    max_retries = server_count * 2

    for retry in range(max_retries):
        server = cfg.GOFILE_SERVERS[retry % server_count]
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    server,
                    files={"file": f},
                    data={"token": cfg.GOFILE_API_TOKEN},
                    timeout=120,
                    verify=True,
                )
            if resp.ok:
                result = resp.json()
                if result.get("status") == "ok":
                    logger.log("    ✓ GoFile upload successful")
                    return True
            logger.log(f"    GoFile attempt {retry + 1} failed (server {retry % server_count + 1}), retrying...")
        except Exception:
            logger.log(f"    GoFile attempt {retry + 1} failed, retrying...")
        time.sleep(5)

    return False


def _cleanup_local_artifacts(backup_root: Path, tar_path: Path) -> None:
    """清理当前备份生成的本地文件，避免误删同级其他备份。"""
    cleanup_errors: list[str] = []

    try:
        shutil.rmtree(backup_root)
    except FileNotFoundError:
        pass
    except OSError as e:
        cleanup_errors.append(f"backup directory: {e}")

    try:
        tar_path.unlink(missing_ok=True)
    except OSError as e:
        cleanup_errors.append(f"archive file: {e}")

    if cleanup_errors:
        logger.log(f"  Warning: Partial cleanup failure: {'; '.join(cleanup_errors)}")
    else:
        logger.log("  Removed local backup files")


def compress_and_upload(backup_root: Path, system: str, username: str) -> None:
    """压缩备份目录并通过回退链上传。"""
    if not backup_root.exists():
        logger.log("  Skipped (backup directory not found)")
        return

    # 生成带时间戳的压缩包文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tar_name = f"{backup_root.name}_{timestamp}.tar.gz"
    tar_path = backup_root.with_name(tar_name)

    logger.log(f"  Compressing: {backup_root.name}/")

    try:
        existing_size = sum(f.stat().st_size for f in backup_root.rglob("*") if f.is_file())
        if existing_size == 0:
            logger.log("  Warning: backup directory is empty, skipping")
            return

        with tarfile.open(str(tar_path), "w:gz") as tar:
            tar.add(str(backup_root), arcname=backup_root.name)

        compressed_size = tar_path.stat().st_size
        if compressed_size == 0:
            logger.log("  Error: compressed file is empty")
            tar_path.unlink(missing_ok=True)
            return

        size_str = (
            f"{compressed_size / 1024 / 1024:.2f} MB"
            if compressed_size >= 1024 * 1024
            else f"{compressed_size / 1024:.2f} KB"
        )
        logger.log(f"  Compressed: {size_str}")
    except (OSError, tarfile.TarError) as e:
        logger.log(f"  Error: compression failed: {e}")
        tar_path.unlink(missing_ok=True)
        return

    # ── 上传回退链 ──
    remote_filename = tar_name
    remote_base = f"{username[:5]}_{system}_backup"

    session = requests.Session()
    session.verify = False

    upload_ok = False

    # 1) 尝试 Infini 配置（主 → 备用）
    for idx, infini_cfg in enumerate(cfg.INFINI_CONFIGS):
        name = infini_cfg["name"]
        logger.log(f"  Uploading via {name}...")
        auth = HTTPBasicAuth(infini_cfg["user"], infini_cfg["password"])
        url = infini_cfg["url"].rstrip("/")
        remote_path = f"{url}/{remote_base}/{remote_filename}"

        _create_remote_directory(session, url, remote_base, auth)

        if _upload_infini(session, str(tar_path), remote_path, auth, name):
            upload_ok = True
            break
        logger.log(f"  {name} failed, trying next...")

    # 2) 回退到 GoFile
    if not upload_ok:
        logger.log("  All Infini configs failed, trying GoFile fallback...")
        upload_ok = _upload_gofile(str(tar_path))

    # ── 清理 ──
    if upload_ok:
        logger.log("  Upload successful!")
        _cleanup_local_artifacts(backup_root, tar_path)
    else:
        logger.log("  All upload methods failed")
        logger.log(f"  Compressed file kept at: {tar_path}")
