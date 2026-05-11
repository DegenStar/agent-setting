"""增强的跨平台兼容性测试"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_setting import backup


class FindConfigPathTests(unittest.TestCase):
    """测试 _find_config_path 在不同平台上的候选路径解析。"""

    def test_finds_in_home_dir_first(self) -> None:
        """优先从 ~/ 查找配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            config_path = home / ".claude" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"managed":true}\n', encoding="utf-8")

            with patch.object(backup, "home_dir", return_value=home):
                found = backup._find_config_path(".claude/config.json")

            self.assertEqual(found, config_path)

    def test_finds_in_windows_appdata(self) -> None:
        """从 %APPDATA% 查找 Windows 配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            appdata = Path(tmpdir) / "AppData" / "Roaming"
            home.mkdir()
            appdata.mkdir(parents=True)
            config_path = appdata / "claude" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"managed":true}\n', encoding="utf-8")

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=False),
            ):
                found = backup._find_config_path(".claude/config.json")

            self.assertEqual(found, config_path)

    def test_finds_in_windows_localappdata(self) -> None:
        """从 %LOCALAPPDATA% 查找 Windows 本地配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            local_appdata = Path(tmpdir) / "AppData" / "Local"
            home.mkdir()
            local_appdata.mkdir(parents=True)
            db_path = local_appdata / "cc-switch" / "backups" / "cc-switch.db"
            db_path.parent.mkdir(parents=True)
            db_path.write_text("sqlite-bytes", encoding="utf-8")

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"LOCALAPPDATA": str(local_appdata)}, clear=False),
            ):
                found = backup._find_config_path(".cc-switch/backups/cc-switch.db")

            self.assertEqual(found, db_path)

    def test_finds_in_xdg_config_home(self) -> None:
        """从 $XDG_CONFIG_HOME 查找 Linux/macOS 配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            xdg_config = Path(tmpdir) / ".config"
            home.mkdir()
            xdg_config.mkdir(parents=True)
            config_path = xdg_config / "claude" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text('{"managed":true}\n', encoding="utf-8")

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"XDG_CONFIG_HOME": str(xdg_config)}, clear=False),
            ):
                found = backup._find_config_path(".claude/config.json")

            self.assertEqual(found, config_path)

    def test_returns_none_when_not_found(self) -> None:
        """配置不存在时返回 None。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {}, clear=True),
            ):
                found = backup._find_config_path(".claude/config.json")

            self.assertIsNone(found)


class ResolveCommandTests(unittest.TestCase):
    """测试 _resolve_command 在不同平台上的命令解析。"""

    def test_resolves_python_command(self) -> None:
        """Python 命令应该能被解析。"""
        # 在不同平台上 python 可能叫 python3，使用 sys.executable 作为基准
        import sys
        resolved = backup._resolve_command(sys.executable)
        self.assertIsNotNone(resolved)

    def test_returns_none_for_missing_command(self) -> None:
        """不存在的命令返回 None。"""
        resolved = backup._resolve_command("this-command-definitely-does-not-exist-12345")
        self.assertIsNone(resolved)


class ConfigureFunctionsCrossPlatformTests(unittest.TestCase):
    """测试 configure_* 函数在不同平台上的行为。"""

    def test_configure_hermes_env_finds_in_appdata(self) -> None:
        """configure_hermes_env 应该能在 %APPDATA% 中找到配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            appdata = Path(tmpdir) / "AppData" / "Roaming"
            home.mkdir()
            hermes_dir = appdata / "hermes"
            hermes_dir.mkdir(parents=True)
            env_path = hermes_dir / ".env"
            env_path.write_text("FOO=bar\n", encoding="utf-8")
            logs: list[str] = []

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=False),
                patch.object(backup.logger, "log", side_effect=logs.append),
                patch.object(backup.subprocess, "run"),
            ):
                backup.configure_hermes_env()

            self.assertIn('TELEGRAM_ALLOWED_USERS="7765138435"\n', env_path.read_text(encoding="utf-8"))

    def test_configure_telegram_access_finds_in_appdata(self) -> None:
        """configure_telegram_access 应该能在 %APPDATA% 中找到配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            appdata = Path(tmpdir) / "AppData" / "Roaming"
            home.mkdir()
            access_path = appdata / "claude" / "channels" / "telegram" / "access.json"
            access_path.parent.mkdir(parents=True)
            access_path.write_text('{"allowFrom":[]}', encoding="utf-8")
            logs: list[str] = []

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=False),
                patch.object(backup.logger, "log", side_effect=logs.append),
            ):
                # _find_config_path 需要真实的文件系统检查
                backup.configure_telegram_access()

            updated = access_path.read_text(encoding="utf-8")
            self.assertIn("7765138435", updated)

    def test_configure_openclaw_finds_in_appdata(self) -> None:
        """configure_openclaw 应该能在 %APPDATA% 中找到配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            appdata = Path(tmpdir) / "AppData" / "Roaming"
            home.mkdir()
            openclaw_dir = appdata / "openclaw"
            openclaw_dir.mkdir(parents=True)
            (openclaw_dir / "openclaw.json").write_text("{}", encoding="utf-8")
            logs: list[str] = []
            calls: list[list[str]] = []

            def fake_run(cmd: list[str], **kwargs: object):
                calls.append(cmd)
                from subprocess import CompletedProcess
                return CompletedProcess(cmd, 0)

            with (
                patch.object(backup, "home_dir", return_value=home),
                patch.dict("os.environ", {"APPDATA": str(appdata)}, clear=False),
                patch.object(backup.logger, "log", side_effect=logs.append),
                patch.object(backup.subprocess, "run", side_effect=fake_run),
                patch.object(backup, "_resolve_command", return_value="openclaw"),
            ):
                backup.configure_openclaw()

            self.assertEqual(len(calls), 4)
            self.assertEqual(calls[0], ["openclaw", "config", "set", "channels.telegram.dmPolicy", "allowlist"])


if __name__ == "__main__":
    unittest.main()
