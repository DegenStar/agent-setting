import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_setting import backup


class BackupCommandSafetyTests(unittest.TestCase):
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
            self.assertEqual(run_mock.call_args.args[0], ["hermes", "gateway", "restart"])
            self.assertEqual(kwargs["check"], False)
            self.assertEqual(kwargs["timeout"], backup.COMMAND_TIMEOUT_SECONDS)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["capture_output"], True)
            self.assertEqual(kwargs["text"], True)
            self.assertTrue(any("timed out" in message for message in logs))

    def test_configure_openclaw_continues_after_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            openclaw_dir = home / ".openclaw"
            openclaw_dir.mkdir(parents=True)
            (openclaw_dir / "openclaw.json").write_text("{}", encoding="utf-8")
            logs: list[str] = []
            calls: list[list[str]] = []

            def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(cmd)
                self.assertEqual(kwargs["check"], False)
                self.assertEqual(kwargs["timeout"], backup.COMMAND_TIMEOUT_SECONDS)
                self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
                self.assertEqual(kwargs["capture_output"], True)
                self.assertEqual(kwargs["text"], True)
                if cmd[-1] == "allowlist":
                    return subprocess.CompletedProcess(cmd, 1)
                return subprocess.CompletedProcess(cmd, 0)

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.object(backup.logger, "log", side_effect=logs.append),
                patch.object(backup, "_resolve_command", return_value="/usr/bin/openclaw"),
                patch.object(backup.subprocess, "run", side_effect=fake_run),
            ):
                backup.configure_openclaw()

            self.assertEqual(
                calls,
                [
                    ["openclaw", "config", "set", "channels.telegram.dmPolicy", "allowlist"],
                    ["openclaw", "config", "set", "channels.telegram.allowFrom", "*"],
                    ["openclaw", "config", "set", "channels.telegram.groupPolicy", "open"],
                    ["openclaw", "gateway", "restart"],
                ],
            )
            self.assertTrue(any("exited with code 1" in message for message in logs))

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
