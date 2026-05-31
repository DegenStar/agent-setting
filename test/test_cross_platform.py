import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_setting import backup, config, detector, logger, uploader


class DetectorTests(unittest.TestCase):
    def test_detect_system_recognizes_wsl_from_environment(self) -> None:
        with (
            patch("sys.platform", "linux"),
            patch("getpass.getuser", return_value="tester"),
            patch.dict("os.environ", {"WSL_DISTRO_NAME": "Ubuntu"}, clear=True),
        ):
            system, username = detector.detect_system()

        self.assertEqual((system, username), ("wsl", "tester"))

    def test_detect_system_recognizes_windows(self) -> None:
        with (
            patch("sys.platform", "win32"),
            patch("getpass.getuser", return_value="tester"),
        ):
            system, username = detector.detect_system()

        self.assertEqual((system, username), ("wins", "tester"))


class LoggerTests(unittest.TestCase):
    def tearDown(self) -> None:
        logger._log_path = None

    def test_log_ignores_stdout_encoding_because_it_writes_only_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.setup_log(Path(tmpdir) / "backup.log")
            stdout = io.StringIO()

            with patch("sys.stdout", stdout):
                logger.log("    ✓ uploaded")

            self.assertEqual(stdout.getvalue(), "")
            log_file = next(Path(tmpdir).glob("backup-*.log"))
            self.assertIn("uploaded", log_file.read_text(encoding="utf-8"))


class BackupResilienceTests(unittest.TestCase):
    def test_backup_configs_supports_windows_program_files_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            appdata = root / "AppData" / "Roaming"
            backup_root = root / "backup"
            home.mkdir()
            config_path = appdata / "claude" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"managed":true}\n', encoding="utf-8")

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=False),
            ):
                backup.backup_configs(backup_root)

            copied = backup_root / ".claude" / "config.json"
            self.assertTrue(copied.exists())
            self.assertEqual(copied.read_text(encoding="utf-8"), '{"managed":true}\n')

    def test_backup_configs_supports_hermes_appdata_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            appdata = root / "AppData" / "Roaming"
            backup_root = root / "backup"
            home.mkdir()
            hermes_path = appdata / "hermes" / "config.yaml"
            hermes_path.parent.mkdir(parents=True)
            hermes_path.write_text("bot: enabled\n", encoding="utf-8")

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=False),
            ):
                backup.backup_configs(backup_root)

            copied = backup_root / ".hermes" / "config.yaml"
            self.assertTrue(copied.exists())
            self.assertEqual(copied.read_text(encoding="utf-8"), "bot: enabled\n")

    def test_backup_configs_supports_cc_switch_localappdata_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            local_appdata = root / "AppData" / "Local"
            backup_root = root / "backup"
            home.mkdir()
            db_path = local_appdata / "cc-switch" / "backups" / "cc-switch.db"
            db_path.parent.mkdir(parents=True)
            db_path.write_text("sqlite-bytes", encoding="utf-8")

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"LOCALAPPDATA": str(local_appdata)}, clear=False),
            ):
                backup.backup_configs(backup_root)

            copied = backup_root / ".cc-switch" / "backups" / "cc-switch.db"
            self.assertTrue(copied.exists())
            self.assertEqual(copied.read_text(encoding="utf-8"), "sqlite-bytes")

    def test_configure_hermes_env_skips_unreadable_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            hermes_dir = home / ".hermes"
            hermes_dir.mkdir(parents=True)
            env_path = hermes_dir / ".env"
            env_path.write_text("FOO=bar\n", encoding="utf-8")
            logs: list[str] = []

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.object(backup.logger, "log", side_effect=logs.append),
                patch.object(Path, "read_text", side_effect=OSError("locked")),
            ):
                backup.configure_hermes_env()

            self.assertTrue(any("Failed to read .hermes/.env" in message for message in logs))

    def test_configure_telegram_access_skips_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            access_path = home / ".claude" / "channels" / "telegram" / "access.json"
            access_path.parent.mkdir(parents=True)
            access_path.write_text('{"allowFrom":[]}', encoding="utf-8")
            logs: list[str] = []

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.object(backup.logger, "log", side_effect=logs.append),
                patch.object(Path, "write_text", side_effect=OSError("denied")),
            ):
                backup.configure_telegram_access()

            self.assertTrue(any("Failed to write access.json" in message for message in logs))


class UploaderCleanupTests(unittest.TestCase):
    def test_cleanup_removes_only_current_backup_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            backup_root = home / ".dev" / "agents-Backup" / "alice_linux_agent-setting"
            sibling_root = home / ".dev" / "agents-Backup" / "bob_linux_agent-setting"
            backup_root.mkdir(parents=True)
            sibling_root.mkdir(parents=True)
            (backup_root / "config.txt").write_text("data", encoding="utf-8")
            (sibling_root / "keep.txt").write_text("keep", encoding="utf-8")
            logs: list[str] = []

            session = MagicMock()
            session.put.return_value.status_code = 201

            with (
                patch.object(uploader.logger, "log", side_effect=logs.append),
                patch.object(config, "INFINI_CONFIGS", [{"name": "Test", "url": "https://example.com/dav/", "user": "u", "password": "p"}]),
                patch.object(uploader.requests, "Session", return_value=session),
                patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
            ):
                uploader.compress_and_upload(backup_root, "linux", "alice")

            self.assertFalse(backup_root.exists())
            self.assertTrue(sibling_root.exists())
            tarballs = list((home / ".dev" / "agents-Backup").glob("alice_linux_agent-setting_*.tar.gz"))
            self.assertEqual(tarballs, [])
            self.assertTrue(any("Removed local backup files" in message for message in logs))


if __name__ == "__main__":
    unittest.main()
