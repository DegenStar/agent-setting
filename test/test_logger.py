import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_setting import logger


class LoggerTests(unittest.TestCase):
    def tearDown(self) -> None:
        logger._log_path = None

    def test_log_writes_only_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "backup.log"
            logger.setup_log(log_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                logger.log("hello")

            self.assertEqual(stdout.getvalue(), "")
            self.assertFalse(log_path.exists())

            timestamped_logs = list(Path(tmpdir).glob("backup-*.log"))
            self.assertEqual(len(timestamped_logs), 1)
            self.assertRegex(timestamped_logs[0].name, r"^backup-\d{8}-\d{6}\.log$")
            self.assertIn("hello", timestamped_logs[0].read_text(encoding="utf-8"))

    def test_error_writes_to_log_and_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger.setup_log(Path(tmpdir) / "backup.log")
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                logger.error("permission denied")

            self.assertEqual(stderr.getvalue(), "permission denied\n")
            log_path = next(Path(tmpdir).glob("backup-*.log"))
            self.assertIn("permission denied", log_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
