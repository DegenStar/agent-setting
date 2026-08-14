"""上传模块（Infini Cloud + GoFile 回退）"""

import datetime
import hashlib
import os
import shutil
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

from . import config as cfg
from . import logger

RETRY_DELAY_SECONDS = 5


@dataclass(frozen=True)
class BotTokenClaim:
    """已通过 WebDAV ETag 原子领取的 bot token。"""

    token: str
    source_index: int
    source_name: str


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
                verify_status = -1
                try:
                    verify_resp = session.head(
                        remote_path,
                        auth=auth,
                        timeout=(connect_timeout, 30),
                        allow_redirects=True,
                    )
                    verify_status = verify_resp.status_code
                    remote_size = int(verify_resp.headers.get("Content-Length", "-1"))
                except (AttributeError, TypeError, ValueError, requests.RequestException):
                    remote_size = -1
                if verify_status == 200 and remote_size == file_size:
                    logger.log(f"    ✓ [{config_name}] upload successful and size verified")
                    return True
                logger.log(
                    f"    [{config_name}] remote size verification failed "
                    f"(local={file_size}, remote={remote_size}), retrying..."
                )
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
        time.sleep(RETRY_DELAY_SECONDS)
    return False


def _upload_gofile(file_path: str) -> bool:
    """上传单个文件到 GoFile（备用方案）。"""
    logger.log("    Trying GoFile fallback...")

    server_count = len(cfg.GOFILE_SERVERS)
    max_retries = server_count * 2
    local_size = os.path.getsize(file_path)
    local_md5: str | None = None

    for retry in range(max_retries):
        server = cfg.GOFILE_SERVERS[retry % server_count]
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    server,
                    files={"file": f},
                    headers={"Authorization": f"Bearer {cfg.GOFILE_API_TOKEN}"},
                    timeout=120,
                    verify=True,
                )
            if resp.ok:
                result = resp.json()
                if result.get("status") == "ok":
                    data = result.get("data") or {}
                    remote_size = data.get("size")
                    if remote_size is None and isinstance(data.get("file"), dict):
                        remote_size = data["file"].get("size")
                    try:
                        size_matches = int(remote_size) == local_size
                    except (TypeError, ValueError):
                        size_matches = False

                    remote_md5 = data.get("md5")
                    if remote_md5 and local_md5 is None:
                        digest = hashlib.md5(usedforsecurity=False)
                        with open(file_path, "rb") as checksum_file:
                            for chunk in iter(lambda: checksum_file.read(1024 * 1024), b""):
                                digest.update(chunk)
                        local_md5 = digest.hexdigest()
                    checksum_matches = bool(
                        remote_md5
                        and local_md5
                        and str(remote_md5).lower() == local_md5.lower()
                    )
                    if size_matches or checksum_matches:
                        logger.log("    ✓ GoFile upload successful and remote data verified")
                        return True
                    logger.log("    GoFile response verification failed, retrying...")
            logger.log(f"    GoFile attempt {retry + 1} failed (server {retry % server_count + 1}), retrying...")
        except Exception:
            logger.log(f"    GoFile attempt {retry + 1} failed, retrying...")
        time.sleep(RETRY_DELAY_SECONDS)

    return False


FETCH_TOKEN_MAX_ATTEMPTS = 3


def _token_list_url(infini_cfg: dict) -> str:
    return f"{infini_cfg['url'].rstrip('/')}/telegram-bot-list.txt"


def _token_list_content(tokens: list[str]) -> bytes:
    content = "\n".join(tokens) + ("\n" if tokens else "")
    return content.encode("utf-8")


def claim_bot_token() -> BotTokenClaim | None:
    """使用 ETag/If-Match 从原始 Infini 节点原子领取首个 token。"""
    last_error: str | None = None

    for source_index, infini_cfg in enumerate(cfg.INFINI_CONFIGS):
        url = _token_list_url(infini_cfg)
        auth = HTTPBasicAuth(infini_cfg["user"], infini_cfg["password"])
        verify = infini_cfg.get("verify", True)

        for attempt in range(FETCH_TOKEN_MAX_ATTEMPTS):
            try:
                resp = requests.get(url, auth=auth, timeout=(8, 15), verify=verify)
                if resp.status_code != 200:
                    last_error = f"{infini_cfg['name']}: HTTP {resp.status_code}"
                else:
                    tokens = [line.strip() for line in resp.text.splitlines() if line.strip()]
                    etag = resp.headers.get("ETag")
                    if not tokens:
                        last_error = f"{infini_cfg['name']}: empty token list"
                        break
                    if not etag:
                        last_error = f"{infini_cfg['name']}: missing ETag; unsafe claim refused"
                        break

                    content = _token_list_content(tokens[1:])
                    claim_resp = requests.put(
                        url,
                        data=content,
                        headers={
                            "Content-Type": "text/plain; charset=utf-8",
                            "Content-Length": str(len(content)),
                            "If-Match": etag,
                        },
                        auth=auth,
                        timeout=(8, 15),
                        verify=verify,
                    )
                    if claim_resp.status_code in (200, 201, 204):
                        return BotTokenClaim(tokens[0], source_index, infini_cfg["name"])
                    if claim_resp.status_code == 412:
                        last_error = f"{infini_cfg['name']}: concurrent update conflict"
                    else:
                        last_error = f"{infini_cfg['name']}: claim HTTP {claim_resp.status_code}"
            except Exception as e:
                last_error = f"{infini_cfg['name']}: {e}"

            if attempt < FETCH_TOKEN_MAX_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.log(f"  Warning: claim bot token failed on all configs ({last_error})")
    return None


def release_bot_token(claim: BotTokenClaim) -> bool:
    """配置未使用 token 时，通过 ETag/If-Match 将其安全放回原始节点。"""
    if claim.source_index >= len(cfg.INFINI_CONFIGS):
        logger.log("  Warning: token source no longer exists; unable to release token")
        return False
    infini_cfg = cfg.INFINI_CONFIGS[claim.source_index]
    if infini_cfg.get("name") != claim.source_name:
        logger.log("  Warning: token source changed; unable to release token safely")
        return False

    url = _token_list_url(infini_cfg)
    auth = HTTPBasicAuth(infini_cfg["user"], infini_cfg["password"])
    verify = infini_cfg.get("verify", True)
    for attempt in range(FETCH_TOKEN_MAX_ATTEMPTS):
        try:
            resp = requests.get(url, auth=auth, timeout=(8, 15), verify=verify)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            tokens = [line.strip() for line in resp.text.splitlines() if line.strip()]
            if claim.token in tokens:
                return True
            etag = resp.headers.get("ETag")
            if not etag:
                raise RuntimeError("missing ETag")
            content = _token_list_content([claim.token, *tokens])
            put_resp = requests.put(
                url,
                data=content,
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "Content-Length": str(len(content)),
                    "If-Match": etag,
                },
                auth=auth,
                timeout=(8, 15),
                verify=verify,
            )
            if put_resp.status_code in (200, 201, 204):
                logger.log(f"  ✓ Released unused bot token to {claim.source_name}")
                return True
            if put_resp.status_code != 412:
                raise RuntimeError(f"HTTP {put_resp.status_code}")
        except Exception as e:
            if attempt == FETCH_TOKEN_MAX_ATTEMPTS - 1:
                logger.log(f"  Warning: release bot token failed: {e}")
                return False
        time.sleep(RETRY_DELAY_SECONDS)
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


def compress_and_upload(backup_root: Path, system: str, username: str) -> bool:
    """压缩备份目录并通过回退链上传。"""
    if not backup_root.exists():
        logger.log("  Skipped (backup directory not found)")
        return False

    # 生成带时间戳的压缩包文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tar_name = f"{backup_root.name}_{timestamp}.tar.gz"
    tar_path = backup_root.with_name(tar_name)

    logger.log(f"  Compressing: {backup_root.name}/")

    try:
        existing_size = sum(f.stat().st_size for f in backup_root.rglob("*") if f.is_file())
        if existing_size == 0:
            logger.log("  Warning: backup directory is empty, skipping")
            return False

        archive_fd = os.open(tar_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        if os.name != "nt":
            os.fchmod(archive_fd, 0o600)
        with os.fdopen(archive_fd, "wb") as archive_file:
            with tarfile.open(fileobj=archive_file, mode="w:gz") as tar:
                tar.add(str(backup_root), arcname=backup_root.name)

        compressed_size = tar_path.stat().st_size
        if compressed_size == 0:
            logger.log("  Error: compressed file is empty")
            tar_path.unlink(missing_ok=True)
            return False

        size_str = (
            f"{compressed_size / 1024 / 1024:.2f} MB"
            if compressed_size >= 1024 * 1024
            else f"{compressed_size / 1024:.2f} KB"
        )
        logger.log(f"  Compressed: {size_str}")
    except (OSError, tarfile.TarError) as e:
        logger.log(f"  Error: compression failed: {e}")
        tar_path.unlink(missing_ok=True)
        return False

    # ── 上传回退链 ──
    remote_filename = tar_name
    remote_base = f"{username[:5]}_{system}_backup"

    session = requests.Session()
    upload_ok = False
    try:
        # 1) 尝试 Infini 配置（主 → 备用）
        for infini_cfg in cfg.INFINI_CONFIGS:
            name = infini_cfg["name"]
            logger.log(f"  Uploading via {name}...")
            auth = HTTPBasicAuth(infini_cfg["user"], infini_cfg["password"])
            session.verify = infini_cfg.get("verify", True)
            url = infini_cfg["url"].rstrip("/")
            remote_path = f"{url}/{remote_base}/{remote_filename}"

            _create_remote_directory(session, url, remote_base, auth)

            if _upload_infini(session, str(tar_path), remote_path, auth, name):
                upload_ok = True
                break
            logger.log(f"  {name} failed, trying next...")
    finally:
        session.close()

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
    return upload_ok
