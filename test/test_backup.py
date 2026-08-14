import json
import getpass
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_setting import backup


class BackupCommandSafetyTests(unittest.TestCase):
    def test_atomic_write_failure_preserves_original_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "settings.json"
            target.write_text("original", encoding="utf-8")

            with patch.object(backup, "_replace_file", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    backup._atomic_write_text(target, "replacement")

            self.assertEqual(target.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_atomic_write_preserves_extended_attributes(self) -> None:
        if not all(hasattr(os, name) for name in ("setxattr", "getxattr")):
            self.skipTest("extended attributes are not supported")
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "settings.json"
            target.write_text("original", encoding="utf-8")
            attribute = b"user.agent_setting_test"
            try:
                os.setxattr(target, attribute, b"preserve-me")
            except OSError:
                self.skipTest("extended attributes are unavailable on this filesystem")

            backup._atomic_write_text(target, "replacement")

            self.assertEqual(os.getxattr(target, attribute), b"preserve-me")

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific metadata test")
    def test_atomic_write_preserves_macos_xattrs_and_acl(self) -> None:
        if not shutil.which("xattr") or not shutil.which("chmod"):
            self.skipTest("macOS metadata tools are unavailable")
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "settings.json"
            target.write_text("original", encoding="utf-8")
            subprocess.run(
                ["xattr", "-w", "com.agent-setting.test", "preserve-me", str(target)],
                check=True,
            )
            subprocess.run(
                ["chmod", "+a", f"{getpass.getuser()} allow read,write", str(target)],
                check=True,
            )

            backup._atomic_write_text(target, "replacement")

            xattr = subprocess.run(
                ["xattr", "-p", "com.agent-setting.test", str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            acl = subprocess.run(
                ["ls", "-le", str(target)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(xattr.stdout.strip(), "preserve-me")
            self.assertIn("allow read,write", acl.stdout)

    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific metadata test")
    def test_backup_copy_preserves_macos_xattrs(self) -> None:
        if not shutil.which("xattr"):
            self.skipTest("macOS xattr tool is unavailable")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "config.json"
            destination = root / "backup"
            source.write_text("data", encoding="utf-8")
            subprocess.run(
                ["xattr", "-w", "com.agent-setting.test", "preserve-me", str(source)],
                check=True,
            )

            self.assertTrue(backup.copy_to_backup(source, destination, "config.json"))

            copied = destination / "config.json"
            xattr = subprocess.run(
                ["xattr", "-p", "com.agent-setting.test", str(copied)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(xattr.stdout.strip(), "preserve-me")

    def test_copy_to_backup_skips_symlinks_outside_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source"
            source.mkdir()
            (source / "config.txt").write_text("safe", encoding="utf-8")
            outside = root / "outside-secret.txt"
            outside.write_text("secret", encoding="utf-8")
            link = source / "outside-link"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are not available on this platform")

            destination = root / "backup"
            backup.copy_to_backup(source, destination, "source")

            self.assertTrue((destination / "source" / "config.txt").exists())
            self.assertFalse((destination / "source" / "outside-link").exists())

    def test_copy_to_backup_skips_uninspectable_source(self) -> None:
        source = Path("C:/denied/config.json")
        logs: list[str] = []
        with (
            patch.object(Path, "is_symlink", autospec=True, side_effect=PermissionError("denied")),
            patch.object(backup.logger, "log", side_effect=logs.append),
        ):
            copied = backup.copy_to_backup(source, Path("C:/backup"), "config.json")

        self.assertFalse(copied)
        self.assertTrue(any("unable to inspect" in message for message in logs))

    def test_configure_hermes_env_skips_timeout_during_restart(self) -> None:
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
                patch.object(backup, "_resolve_command", return_value="C:/tools/hermes.cmd"),
                patch.object(
                    backup.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(
                        cmd=["hermes", "gateway", "restart"],
                        timeout=backup.COMMAND_TIMEOUT_SECONDS,
                    ),
                ) as run_mock,
            ):
                backup.configure_hermes_env()

            self.assertIn('TELEGRAM_ALLOWED_USERS="7765138435"\n', env_path.read_text(encoding="utf-8"))
            run_mock.assert_called_once()
            _, kwargs = run_mock.call_args
            self.assertEqual(
                run_mock.call_args.args[0],
                ["C:/tools/hermes.cmd", "gateway", "restart"],
            )
            self.assertEqual(kwargs["check"], False)
            self.assertEqual(kwargs["timeout"], backup.COMMAND_TIMEOUT_SECONDS)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["capture_output"], True)
            self.assertNotIn("text", kwargs)
            self.assertTrue(any("timed out" in message for message in logs))

    def test_configure_openclaw_writes_json_with_correct_order(self) -> None:
        """configure_openclaw 应直接写入 JSON：先填 allowFrom，再设 allowlist。"""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            openclaw_dir = home / ".openclaw"
            openclaw_dir.mkdir(parents=True)
            json_path = openclaw_dir / "openclaw.json"
            json_path.write_text("{}", encoding="utf-8")
            logs: list[str] = []
            calls: list[list[str]] = []

            def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(cmd)
                return subprocess.CompletedProcess(cmd, 0)

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.object(backup.logger, "log", side_effect=logs.append),
                patch.object(backup, "_resolve_command", return_value="/usr/bin/openclaw"),
                patch.object(backup.subprocess, "run", side_effect=fake_run),
            ):
                backup.configure_openclaw()

            data = json.loads(json_path.read_text(encoding="utf-8"))
            telegram = data["channels"]["telegram"]
            self.assertEqual(telegram["allowFrom"], ["7765138435"])
            self.assertEqual(telegram["dmPolicy"], "allowlist")
            self.assertEqual(telegram["groupPolicy"], "open")
            # 仅用 CLI 重启网关，不再用 config set
            self.assertEqual(calls, [["/usr/bin/openclaw", "gateway", "restart"]])

    def test_configure_openclaw_preserves_existing_allow_from(self) -> None:
        """已有的 allowFrom 条目应保留并去重。"""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            openclaw_dir = home / ".openclaw"
            openclaw_dir.mkdir(parents=True)
            json_path = openclaw_dir / "openclaw.json"
            json_path.write_text(
                json.dumps({"channels": {"telegram": {"allowFrom": ["111", "111"]}}}),
                encoding="utf-8",
            )

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.object(backup.logger, "log"),
                patch.object(backup, "_resolve_command", return_value="/usr/bin/openclaw"),
                patch.object(backup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
            ):
                backup.configure_openclaw()

            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["channels"]["telegram"]["allowFrom"], ["111", "7765138435"])

    def test_configure_openclaw_new_telegram_uses_allow_from_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            openclaw_dir = home / ".openclaw"
            openclaw_dir.mkdir(parents=True)
            json_path = openclaw_dir / "openclaw.json"
            json_path.write_text("{}", encoding="utf-8")

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.object(backup.logger, "log"),
                patch.object(backup, "_resolve_command", return_value="/usr/bin/openclaw"),
                patch.object(backup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
            ):
                backup.configure_openclaw("bot-token")

            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["channels"]["telegram"]["allowFrom"], ["7765138435"])
            self.assertEqual(data["channels"]["telegram"]["groupPolicy"], "open")

    def test_configure_openclaw_skips_when_command_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            openclaw_dir = home / ".openclaw"
            openclaw_dir.mkdir(parents=True)
            (openclaw_dir / "openclaw.json").write_text("{}", encoding="utf-8")
            logs: list[str] = []

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.object(backup.logger, "log", side_effect=logs.append),
                patch.object(backup, "_resolve_command", return_value=None),
            ):
                backup.configure_openclaw()

            self.assertTrue(any("'openclaw' command not found" in message for message in logs))


if __name__ == "__main__":
    unittest.main()
