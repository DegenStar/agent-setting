import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_setting import config, uploader


class RemoteDirectoryTests(unittest.TestCase):
    def test_remote_directory_uses_detected_system_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir) / "alice_wins_agent-setting"
            backup_root.mkdir()
            (backup_root / "config.txt").write_text("data", encoding="utf-8")

            session = MagicMock()
            session.put.return_value.status_code = 201

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

            with (
                patch.object(uploader.logger, "log"),
                patch.object(config, "INFINI_CONFIGS", [{"name": "Test", "url": "https://example.com/dav/", "user": "u", "password": "p"}]),
                patch.object(uploader.requests, "Session", return_value=session),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                uploader.compress_and_upload(backup_root, "linux", "alice")

            self.assertTrue(session.verify)

    def test_infini_upload_can_disable_tls_verification_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_root = Path(tmpdir) / "alice_linux_agent-setting"
            backup_root.mkdir()
            (backup_root / "config.txt").write_text("data", encoding="utf-8")

            session = MagicMock()
            session.put.return_value.status_code = 201

            with (
                patch.object(uploader.logger, "log"),
                patch.object(config, "INFINI_CONFIGS", [{"name": "Test", "url": "https://example.com/dav/", "user": "u", "password": "p", "verify": False}]),
                patch.object(uploader.requests, "Session", return_value=session),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                uploader.compress_and_upload(backup_root, "linux", "alice")

            self.assertFalse(session.verify)


if __name__ == "__main__":
    unittest.main()
