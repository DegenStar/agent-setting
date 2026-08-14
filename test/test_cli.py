import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_setting import cli
from agent_setting.uploader import BotTokenClaim


class CliExitStatusTests(unittest.TestCase):
    def test_main_ignores_script_download_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "backup"
            staging = Path(tmpdir) / "staging"
            staging.mkdir()

            with (
                patch.object(cli, "detect_system", return_value=("linux", "alice")),
                patch.object(cli, "get_backup_root", return_value=base),
                patch.object(cli, "create_backup_staging_root", return_value=staging),
                patch.object(cli.logger, "setup_log"),
                patch.object(cli.logger, "log"),
                patch.object(cli.logger, "console"),
                patch.object(cli, "download_agent_scripts", return_value=False) as download_mock,
                patch.object(cli, "backup_configs"),
                patch.object(cli, "claim_bot_token", return_value=None),
                patch.object(cli, "configure_hermes_env"),
                patch.object(cli, "configure_openclaw"),
                patch.object(cli, "configure_telegram_access"),
                patch.object(cli, "compress_and_upload", return_value=True),
            ):
                result = cli.main()

            self.assertEqual(result, 0)
            download_mock.assert_called_once_with("linux")

    def test_main_returns_failure_when_all_uploads_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "backup"
            staging = Path(tmpdir) / "staging"
            staging.mkdir()

            with (
                patch.object(cli, "detect_system", return_value=("linux", "alice")),
                patch.object(cli, "get_backup_root", return_value=base),
                patch.object(cli, "create_backup_staging_root", return_value=staging),
                patch.object(cli.logger, "setup_log"),
                patch.object(cli.logger, "log"),
                patch.object(cli.logger, "error"),
                patch.object(cli, "backup_configs"),
                patch.object(cli, "download_agent_scripts"),
                patch.object(cli, "claim_bot_token", return_value=None),
                patch.object(cli, "configure_hermes_env"),
                patch.object(cli, "configure_openclaw"),
                patch.object(cli, "configure_telegram_access"),
                patch.object(cli, "compress_and_upload", return_value=False),
            ):
                result = cli.main()

            self.assertEqual(result, 1)

    def test_main_returns_failure_when_unused_token_cannot_be_released(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "backup"
            staging = Path(tmpdir) / "staging"
            staging.mkdir()
            claim = BotTokenClaim("token-a", 0, "Primary")

            with (
                patch.object(cli, "detect_system", return_value=("linux", "alice")),
                patch.object(cli, "get_backup_root", return_value=base),
                patch.object(cli, "create_backup_staging_root", return_value=staging),
                patch.object(cli.logger, "setup_log"),
                patch.object(cli.logger, "log"),
                patch.object(cli.logger, "error"),
                patch.object(cli, "backup_configs"),
                patch.object(cli, "download_agent_scripts"),
                patch.object(cli, "claim_bot_token", return_value=claim),
                patch.object(cli, "configure_hermes_env"),
                patch.object(cli, "configure_openclaw"),
                patch.object(cli, "check_hermes_has_bot_token", return_value=False),
                patch.object(cli, "check_openclaw_has_bot_token", return_value=False),
                patch.object(cli, "release_bot_token", return_value=False),
                patch.object(cli, "configure_telegram_access"),
                patch.object(cli, "compress_and_upload", return_value=True),
            ):
                result = cli.main()

            self.assertEqual(result, 1)

    def test_main_releases_claim_when_configuration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "backup"
            staging = Path(tmpdir) / "staging"
            staging.mkdir()
            claim = BotTokenClaim("token-a", 0, "Primary")

            with (
                patch.object(cli, "detect_system", return_value=("linux", "alice")),
                patch.object(cli, "get_backup_root", return_value=base),
                patch.object(cli, "create_backup_staging_root", return_value=staging),
                patch.object(cli.logger, "setup_log"),
                patch.object(cli.logger, "log"),
                patch.object(cli, "backup_configs"),
                patch.object(cli, "download_agent_scripts"),
                patch.object(cli, "claim_bot_token", return_value=claim),
                patch.object(cli, "configure_hermes_env", side_effect=RuntimeError("boom")),
                patch.object(cli, "release_bot_token", return_value=True) as release_mock,
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    cli.main()

            release_mock.assert_called_once_with(claim)


if __name__ == "__main__":
    unittest.main()
