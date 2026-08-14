import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

from agent_setting import script_sync


class ScriptSyncTests(unittest.TestCase):
    def test_windows_downloads_powershell_scripts_to_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            responses = [
                SimpleNamespace(content=b"install-ps1", raise_for_status=lambda: None),
                SimpleNamespace(content=b"setup-ps1", raise_for_status=lambda: None),
            ]

            with (
                patch.object(script_sync.requests, "get", side_effect=responses) as get_mock,
                patch.object(script_sync.logger, "log"),
            ):
                result = script_sync.download_agent_scripts("wins", home)

            target = home / ".local" / "bin"
            self.assertTrue(result)
            self.assertEqual((target / "install.ps1").read_bytes(), b"install-ps1")
            self.assertEqual((target / "SETUP.ps1").read_bytes(), b"setup-ps1")
            self.assertEqual(
                [call.args[0] for call in get_mock.call_args_list],
                [
                    "https://agentskillshub.vercel.app/install.ps1",
                    "https://agentskillshub.vercel.app/src/SETUP.ps1",
                ],
            )

    def test_unix_platforms_download_shell_scripts(self) -> None:
        for system in ("linux", "mac", "wsl"):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as tmpdir:
                home = Path(tmpdir)
                responses = [
                    SimpleNamespace(content=b"install-sh", raise_for_status=lambda: None),
                    SimpleNamespace(content=b"setup-sh", raise_for_status=lambda: None),
                ]
                with (
                    patch.object(script_sync.requests, "get", side_effect=responses),
                    patch.object(script_sync.logger, "log"),
                ):
                    result = script_sync.download_agent_scripts(system, home)

                target = home / ".local" / "bin"
                self.assertTrue(result)
                self.assertEqual((target / "install.sh").read_bytes(), b"install-sh")
                self.assertEqual((target / "SETUP.sh").read_bytes(), b"setup-sh")
                if os.name != "nt":
                    self.assertEqual((target / "install.sh").stat().st_mode & 0o777, 0o755)
                    self.assertEqual((target / "SETUP.sh").stat().st_mode & 0o777, 0o755)

    def test_existing_files_are_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            target = home / ".local" / "bin"
            target.mkdir(parents=True)
            (target / "install.sh").write_bytes(b"old-install")
            (target / "SETUP.sh").write_bytes(b"old-setup")
            (target / "install.sh").chmod(0o700)
            (target / "SETUP.sh").chmod(0o700)
            responses = [
                SimpleNamespace(content=b"new-install", raise_for_status=lambda: None),
                SimpleNamespace(content=b"new-setup", raise_for_status=lambda: None),
            ]

            with (
                patch.object(script_sync.requests, "get", side_effect=responses),
                patch.object(script_sync.logger, "log"),
            ):
                script_sync.download_agent_scripts("linux", home)

            self.assertEqual((target / "install.sh").read_bytes(), b"new-install")
            self.assertEqual((target / "SETUP.sh").read_bytes(), b"new-setup")
            if os.name != "nt":
                self.assertEqual((target / "install.sh").stat().st_mode & 0o777, 0o755)
                self.assertEqual((target / "SETUP.sh").stat().st_mode & 0o777, 0o755)

    def test_failed_download_is_skipped_and_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            target = home / ".local" / "bin"
            target.mkdir(parents=True)
            install_path = target / "install.sh"
            install_path.write_bytes(b"keep-old")
            responses = [
                requests.Timeout("offline"),
                SimpleNamespace(content=b"new-setup", raise_for_status=lambda: None),
            ]
            logs: list[str] = []

            with (
                patch.object(script_sync.requests, "get", side_effect=responses),
                patch.object(script_sync.logger, "log", side_effect=logs.append),
            ):
                result = script_sync.download_agent_scripts("linux", home)

            self.assertFalse(result)
            self.assertEqual(install_path.read_bytes(), b"keep-old")
            self.assertEqual((target / "SETUP.sh").read_bytes(), b"new-setup")
            self.assertTrue(any("Skipped install.sh" in message for message in logs))

    def test_atomic_replace_failure_preserves_old_file_and_removes_temp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "install.sh"
            target.write_bytes(b"keep-old")

            with patch.object(os, "replace", side_effect=OSError("locked")):
                with self.assertRaisesRegex(OSError, "locked"):
                    script_sync._atomic_write_download(target, b"new")

            self.assertEqual(target.read_bytes(), b"keep-old")
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
