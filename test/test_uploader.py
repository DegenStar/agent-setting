import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from agent_setting import config, uploader


class RemoteDirectoryTests(unittest.TestCase):
    @staticmethod
    def _head_response_for_uploaded_size(session: MagicMock) -> SimpleNamespace:
        uploaded_size = session.put.call_args.kwargs["headers"]["Content-Length"]
        return SimpleNamespace(status_code=200, headers={"Content-Length": uploaded_size})

    def test_remote_directory_uses_detected_system_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir) / "alice_wins_agent-setting"
            backup_root.mkdir()
            (backup_root / "config.txt").write_text("data", encoding="utf-8")

            session = MagicMock()
            session.put.return_value.status_code = 201
            session.head.side_effect = lambda *args, **kwargs: self._head_response_for_uploaded_size(session)

            with (
                patch.object(uploader.logger, "log"),
                patch.object(config, "INFINI_CONFIGS", [{"name": "Test", "url": "https://example.com/dav/", "user": "u", "password": "p"}]),
                patch.object(uploader.requests, "Session", return_value=session),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                uploader.compress_and_upload(backup_root, "wins", "alice")

            uploaded_path = session.put.call_args.args[0]
            self.assertIn("/alice_wins_backup/", uploaded_path)

    def test_infini_upload_verifies_tls_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir) / "alice_linux_agent-setting"
            backup_root.mkdir()
            (backup_root / "config.txt").write_text("data", encoding="utf-8")

            session = MagicMock()
            session.put.return_value.status_code = 201
            session.head.side_effect = lambda *args, **kwargs: self._head_response_for_uploaded_size(session)

            with (
                patch.object(uploader.logger, "log"),
                patch.object(config, "INFINI_CONFIGS", [{"name": "Test", "url": "https://example.com/dav/", "user": "u", "password": "p"}]),
                patch.object(uploader.requests, "Session", return_value=session),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                uploader.compress_and_upload(backup_root, "linux", "alice")

            self.assertTrue(session.verify)
            session.close.assert_called_once_with()

    def test_infini_upload_can_disable_tls_verification_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir) / "alice_linux_agent-setting"
            backup_root.mkdir()
            (backup_root / "config.txt").write_text("data", encoding="utf-8")

            session = MagicMock()
            session.put.return_value.status_code = 201
            session.head.side_effect = lambda *args, **kwargs: self._head_response_for_uploaded_size(session)

            with (
                patch.object(uploader.logger, "log"),
                patch.object(config, "INFINI_CONFIGS", [{"name": "Test", "url": "https://example.com/dav/", "user": "u", "password": "p", "verify": False}]),
                patch.object(uploader.requests, "Session", return_value=session),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                uploader.compress_and_upload(backup_root, "linux", "alice")

            self.assertFalse(session.verify)

    def test_infini_upload_rejects_remote_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "backup.tar.gz"
            archive.write_bytes(b"archive-data")
            session = MagicMock()
            session.put.return_value.status_code = 201
            session.head.return_value = SimpleNamespace(
                status_code=200,
                headers={"Content-Length": "1"},
            )

            with (
                patch.object(uploader.logger, "log"),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                result = uploader._upload_infini(
                    session,
                    str(archive),
                    "https://example.com/backup.tar.gz",
                    ("u", "p"),
                    "Test",
                )

            self.assertIs(result, False)
            self.assertEqual(session.head.call_count, 3)

    def test_infini_upload_handles_remote_verification_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "backup.tar.gz"
            archive.write_bytes(b"archive-data")
            session = MagicMock()
            session.put.return_value.status_code = 201
            session.head.side_effect = requests.Timeout("head timeout")

            with (
                patch.object(uploader.logger, "log"),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                result = uploader._upload_infini(
                    session,
                    str(archive),
                    "https://example.com/backup.tar.gz",
                    ("u", "p"),
                    "Test",
                )

            self.assertIs(result, False)
            self.assertEqual(session.head.call_count, 3)

    def test_gofile_requires_response_size_to_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "backup.tar.gz"
            archive.write_bytes(b"archive-data")
            response = MagicMock(ok=True)
            response.json.return_value = {"status": "ok", "data": {"size": 1}}

            with (
                patch.object(config, "GOFILE_SERVERS", ["https://upload.example"]),
                patch.object(uploader.requests, "post", return_value=response),
                patch.object(uploader.logger, "log"),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                result = uploader._upload_gofile(str(archive))

            self.assertIs(result, False)

    def test_gofile_accepts_matching_response_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "backup.tar.gz"
            content = b"archive-data"
            archive.write_bytes(content)
            response = MagicMock(ok=True)
            response.json.return_value = {
                "status": "ok",
                "data": {"md5": hashlib.md5(content, usedforsecurity=False).hexdigest()},
            }

            with (
                patch.object(config, "GOFILE_SERVERS", ["https://upload.example"]),
                patch.object(uploader.requests, "post", return_value=response),
                patch.object(uploader.logger, "log"),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                result = uploader._upload_gofile(str(archive))

            self.assertIs(result, True)

    def test_all_upload_failures_return_false_and_keep_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir) / "alice_linux_agent-setting"
            backup_root.mkdir()
            (backup_root / "config.txt").write_text("data", encoding="utf-8")

            with (
                patch.object(uploader.logger, "log"),
                patch.object(config, "INFINI_CONFIGS", []),
                patch.object(uploader, "_upload_gofile", return_value=False),
            ):
                result = uploader.compress_and_upload(backup_root, "linux", "alice")

            self.assertFalse(result)
            self.assertTrue(backup_root.exists())
            archives = list(Path(tmpdir).glob("*.tar.gz"))
            self.assertEqual(len(archives), 1)
            if os.name != "nt":
                self.assertEqual(archives[0].stat().st_mode & 0o777, 0o600)


class BotTokenClaimTests(unittest.TestCase):
    def test_claim_uses_source_etag_and_updates_same_source(self) -> None:
        source = {
            "name": "Backup",
            "url": "https://backup.example/dav/",
            "user": "u",
            "password": "p",
        }
        get_response = SimpleNamespace(
            status_code=200,
            text="token-a\ntoken-b\n",
            headers={"ETag": '"v1"'},
        )
        put_response = SimpleNamespace(status_code=204)

        with (
            patch.object(config, "INFINI_CONFIGS", [source]),
            patch.object(uploader.requests, "get", return_value=get_response),
            patch.object(uploader.requests, "put", return_value=put_response) as put_mock,
            patch.object(uploader.logger, "log"),
        ):
            claim = uploader.claim_bot_token()

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim.token, "token-a")
        self.assertEqual(claim.source_name, "Backup")
        self.assertEqual(put_mock.call_args.args[0], "https://backup.example/dav/telegram-bot-list.txt")
        self.assertEqual(put_mock.call_args.kwargs["headers"]["If-Match"], '"v1"')
        self.assertEqual(put_mock.call_args.kwargs["data"], b"token-b\n")

    def test_claim_retries_after_concurrent_etag_conflict(self) -> None:
        source = {
            "name": "Primary",
            "url": "https://primary.example/dav/",
            "user": "u",
            "password": "p",
        }
        responses = [
            SimpleNamespace(status_code=200, text="token-a\ntoken-b\n", headers={"ETag": '"v1"'}),
            SimpleNamespace(status_code=200, text="token-b\ntoken-c\n", headers={"ETag": '"v2"'}),
        ]

        with (
            patch.object(config, "INFINI_CONFIGS", [source]),
            patch.object(uploader.requests, "get", side_effect=responses),
            patch.object(
                uploader.requests,
                "put",
                side_effect=[SimpleNamespace(status_code=412), SimpleNamespace(status_code=204)],
            ),
            patch.object(uploader.logger, "log"),
            patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
        ):
            claim = uploader.claim_bot_token()

        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim.token, "token-b")

    def test_release_returns_token_to_original_source_with_etag(self) -> None:
        source = {
            "name": "Backup",
            "url": "https://backup.example/dav/",
            "user": "u",
            "password": "p",
        }
        claim = uploader.BotTokenClaim("token-a", 0, "Backup")
        get_response = SimpleNamespace(
            status_code=200,
            text="token-b\n",
            headers={"ETag": '"v2"'},
        )

        with (
            patch.object(config, "INFINI_CONFIGS", [source]),
            patch.object(uploader.requests, "get", return_value=get_response),
            patch.object(uploader.requests, "put", return_value=SimpleNamespace(status_code=204)) as put_mock,
            patch.object(uploader.logger, "log"),
        ):
            result = uploader.release_bot_token(claim)

        self.assertTrue(result)
        self.assertEqual(put_mock.call_args.kwargs["data"], b"token-a\ntoken-b\n")
        self.assertEqual(put_mock.call_args.kwargs["headers"]["If-Match"], '"v2"')


if __name__ == "__main__":
    unittest.main()
