"""配置结果、保留副本与网络错误的回归测试，全部使用临时目录和模拟网络。"""

import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest
import requests

from agent_setting import backup, cli, config, uploader


@pytest.fixture
def config_target(tmp_path):
    target = tmp_path / "settings"
    with (
        patch.object(backup, "_find_config_path", return_value=target),
        patch.object(backup, "_run_command_safely", return_value=True),
        patch.object(backup.logger, "log"),
    ):
        yield target


@pytest.mark.parametrize("function,content", [
    (backup.configure_hermes_env, "FOO=bar"),
    (backup.configure_openclaw, "{}"),
    (backup.configure_telegram_access, "{}"),
])
def test_config_write_results(config_target, function, content):
    config_target.write_text(content, encoding="utf-8")
    with patch.object(backup, "_atomic_write_text", side_effect=OSError("disk full")):
        assert function() is False
    assert config_target.read_text(encoding="utf-8") == content
    assert function() is True
    if function is backup.configure_hermes_env:
        assert config_target.read_text(encoding="utf-8").startswith("FOO=bar\nTELEGRAM_ALLOWED_USERS=")


@pytest.mark.parametrize("function", [
    backup.configure_hermes_env, backup.configure_openclaw, backup.configure_telegram_access,
])
def test_missing_config_is_skipped(function):
    with patch.object(backup, "_find_config_path", return_value=None):
        assert function() is None


@pytest.mark.parametrize("value", [None, "", "existing-token"])
def test_openclaw_fills_only_empty_token(config_target, value):
    telegram = {"enabled": True, "allowFrom": ["123"]}
    if value is not None:
        telegram["botToken"] = value
    config_target.write_text(json.dumps({"channels": {"telegram": telegram}}), encoding="utf-8")
    assert backup.configure_openclaw("new-token") is True
    result = json.loads(config_target.read_text(encoding="utf-8"))["channels"]["telegram"]
    assert result["botToken"] == (value or "new-token")
    assert result["allowFrom"] == ["123", "7765138435"]
    assert result["enabled"] is True


@pytest.mark.parametrize("function,content", [
    (backup.configure_openclaw, '{"channels": []}'),
    (backup.configure_openclaw, '{"channels": {"telegram": {"allowFrom": [{}]}}}'),
    (backup.configure_telegram_access, "[]"),
    (backup.configure_telegram_access, '{"allowFrom": [{}]}'),
    (backup.configure_telegram_access, "invalid-json"),
])
def test_invalid_config_returns_failure_without_overwrite(config_target, function, content):
    config_target.write_text(content, encoding="utf-8")
    assert function() is False
    assert config_target.read_text(encoding="utf-8") == content


@pytest.fixture
def cli_mocks(tmp_path):
    with ExitStack() as stack:
        defaults = {
            "detect_system": ("linux", "alice"),
            "get_backup_root": tmp_path / "backup",
            "create_backup_staging_root": tmp_path,
            "download_agent_scripts": True,
            "backup_configs": None,
            "claim_bot_token": uploader.BotTokenClaim("test-token", 0, "Primary"),
            "configure_hermes_env": True,
            "configure_openclaw": True,
            "configure_telegram_access": True,
            "check_hermes_has_bot_token": False,
            "check_openclaw_has_bot_token": False,
            "release_bot_token": True,
            "compress_and_upload": True,
        }
        mocks = {name: stack.enter_context(patch.object(cli, name, return_value=value))
                 for name, value in defaults.items()}
        stack.enter_context(patch.object(cli.logger, "setup_log"))
        stack.enter_context(patch.object(cli.logger, "log"))
        mocks["error"] = stack.enter_context(patch.object(cli.logger, "error"))
        yield mocks


@pytest.mark.parametrize("name", ["configure_hermes_env", "configure_openclaw", "configure_telegram_access"])
def test_cli_config_failure_stops_upload_and_releases_unused_token(cli_mocks, name):
    cli_mocks[name].return_value = False
    assert cli.main([]) == 1
    cli_mocks["compress_and_upload"].assert_not_called()
    cli_mocks["release_bot_token"].assert_called_once()
    assert cli_mocks["error"].called


def test_cli_failure_does_not_release_consumed_token(cli_mocks):
    cli_mocks["configure_openclaw"].return_value = False
    cli_mocks["check_hermes_has_bot_token"].return_value = True
    assert cli.main([]) == 1
    cli_mocks["release_bot_token"].assert_not_called()


def test_cli_skip_and_keep_local(cli_mocks):
    for name in ("configure_hermes_env", "configure_openclaw", "configure_telegram_access"):
        cli_mocks[name].return_value = None
    assert cli.main(["--keep-local"]) == 0
    assert cli_mocks["compress_and_upload"].call_args.kwargs == {"keep_local": True}


def test_gofile_empty_servers_does_not_touch_network(tmp_path):
    with patch.object(config, "GOFILE_SERVERS", []), patch.object(uploader.requests, "post") as post:
        assert uploader._upload_gofile(str(tmp_path / "absent")) is False
        post.assert_not_called()


@pytest.mark.parametrize("exception", [requests.Timeout("offline"), ValueError("invalid JSON")])
def test_gofile_records_failure_details(tmp_path, exception):
    archive = tmp_path / "backup.tar.gz"
    archive.write_bytes(b"data")
    with (
        patch.object(config, "GOFILE_SERVERS", ["https://example.test"]),
        patch.object(uploader.requests, "post", side_effect=exception),
        patch.object(uploader, "RETRY_DELAY_SECONDS", 0),
        patch.object(uploader.logger, "log") as log,
    ):
        assert uploader._upload_gofile(str(archive)) is False
        assert any(type(exception).__name__ in call.args[0] and str(exception) in call.args[0]
                   for call in log.call_args_list)


@pytest.mark.parametrize("managed,keep,success,retained", [
    (True, True, True, True),
    (True, False, True, False),
    (True, False, False, True),
    (False, False, True, True),
])
def test_local_cleanup_policy(tmp_path, managed, keep, success, retained):
    root = tmp_path / "backup"
    if managed:
        root = config.create_backup_staging_root(root)
    else:
        root.mkdir()
    (root / "data").write_bytes(b"backup data")
    sibling = tmp_path / "unrelated"
    sibling.write_bytes(b"keep")
    with (
        patch.object(config, "INFINI_CONFIGS", []),
        patch.object(uploader, "_upload_gofile", return_value=success),
        patch.object(uploader.logger, "log"),
    ):
        assert uploader.compress_and_upload(root, "linux", "alice", keep_local=keep) is success
    assert root.exists() is retained
    assert bool(list(tmp_path.glob("*.tar.gz"))) is retained
    assert sibling.read_bytes() == b"keep"


def test_repeated_upload_preserves_previous_archive(tmp_path):
    root = config.create_backup_staging_root(tmp_path / "backup")
    (root / "data").write_bytes(b"first backup")
    with (
        patch.object(config, "INFINI_CONFIGS", []),
        patch.object(uploader, "_upload_gofile", return_value=True),
        patch.object(uploader.datetime, "datetime") as clock,
        patch.object(uploader.logger, "log"),
    ):
        clock.now.return_value.strftime.return_value = "20260911_120000"
        assert uploader.compress_and_upload(root, "linux", "alice", keep_local=True)
        first = next(tmp_path.glob("*.tar.gz"))
        original = first.read_bytes()
        (root / "data").write_bytes(b"second backup")
        assert uploader.compress_and_upload(root, "linux", "alice", keep_local=True)
        assert len(list(tmp_path.glob("*.tar.gz"))) == 2
        assert first.read_bytes() == original


def test_cleanup_refuses_symlink_replacing_managed_directory(tmp_path):
    root = config.create_backup_staging_root(tmp_path / "backup")
    outside = tmp_path / "user-data"
    outside.mkdir()
    (outside / "important").write_bytes(b"keep")
    root.rmdir()
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    archive = root.with_name(f"{root.name}_test.tar.gz")
    archive.write_bytes(b"keep archive")
    uploader._cleanup_local_artifacts(root, archive)
    assert (outside / "important").read_bytes() == b"keep"
    assert archive.read_bytes() == b"keep archive"
